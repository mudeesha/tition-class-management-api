from __future__ import annotations

import secrets

from sqlalchemy.orm import Session

from app.common.schemas import Page, PageParams, add_months, month_of
from app.core import clock
from app.core.exceptions import Conflict, Forbidden, NotFound, RuleViolation
from app.core.security import hash_password
from app.modules.branches.models import Branch
from app.modules.branches.repository import BranchRepository
from app.modules.classes.models import TuitionClass
from app.modules.classes.repository import ClassRepository
from app.modules.institute.repository import CounterRepository
from app.modules.students.models import CardType, Enrollment, EnrollmentStatus, Student
from app.modules.students.repository import EnrollmentRepository, StudentRepository
from app.modules.students.schemas import (
    EnrollmentCreate,
    EnrollmentOut,
    EnrollmentUpdate,
    LeaveIn,
    PortalAccountOut,
    PromoteIn,
    PromoteOut,
    SkippedOut,
    StudentCreate,
    StudentOut,
    StudentProfileOut,
    StudentRef,
    StudentUpdate,
)
from app.modules.users.models import Membership, User
from app.modules.users.repository import MembershipRepository, RoleRepository, UserRepository
from app.tenancy.context import TenantContext
from app.tenancy.limits import ensure_within_limit
from app.tenancy.permissions import RoleKey


def new_qr_token() -> str:
    return secrets.token_urlsafe(24)


class StudentService:
    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.db = db
        self.ctx = ctx
        self.students = StudentRepository(db, ctx)
        self.enrollments = EnrollmentRepository(db, ctx)
        self.branches = BranchRepository(db, ctx)
        self.classes = ClassRepository(db, ctx)
        self.counters = CounterRepository(db, ctx)
        self.users = UserRepository(db)
        self.members = MembershipRepository(db, ctx)
        self.roles = RoleRepository(db, ctx)

    def list(
        self,
        page: PageParams,
        q: str | None,
        branch_id: int | None,
        class_id: int | None,
        grade: int | None,
        is_active: bool | None,
    ) -> Page:
        if branch_id is not None:
            self.ctx.require_branch(branch_id)
        if class_id is not None:
            self.classes.get_or_404(class_id)
        stmt = self.students.search(q, branch_id, class_id, grade, is_active)
        items, total = self.students.paginate(stmt, page.page, page.size)
        return Page(items=items, total=total, page=page.page, size=page.size)

    def get(self, student_id: int) -> Student:
        return self.students.get_or_404(student_id)

    def profile(self, student_id: int) -> StudentProfileOut:
        student = self.get(student_id)
        enrollments = self.enrollments.for_student(student.id)
        return StudentProfileOut(
            **dict(StudentOut.model_validate(student)),
            enrollments=[EnrollmentOut.model_validate(e) for e in enrollments],
        )

    def create(self, data: StudentCreate) -> Student:
        ensure_within_limit(
            self.ctx.tenant.plan.max_students, self.students.count_active(), "students"
        )
        student = Student(
            **data.model_dump(exclude={"home_branch_id", "admitted_on"}),
            home_branch=self._home_branch(data.home_branch_id),
            admitted_on=data.admitted_on or clock.today(),
            code=self._next_code(),
            qr_token=new_qr_token(),
        )
        self.students.add(student)
        self.db.commit()
        return student

    def update(self, student_id: int, data: StudentUpdate) -> Student:
        student = self.get(student_id)
        changes = data.changes()
        if "home_branch_id" in changes:
            student.home_branch = self._home_branch(changes.pop("home_branch_id"))
        if changes.get("is_active") is True and not student.is_active:
            ensure_within_limit(
                self.ctx.tenant.plan.max_students,
                self.students.count_active(),
                "active students",
            )
        for field, value in changes.items():
            setattr(student, field, value)
        if "is_active" in changes and (membership := self._portal_membership(student)):
            # Inactive students can't use the portal.
            membership.is_active = student.is_active
        self.db.commit()
        return student

    # Portal login

    def portal_account(self, student_id: int) -> PortalAccountOut:
        student = self.get(student_id)
        membership = self._portal_membership(student)
        return PortalAccountOut(
            username=student.user.username if student.user else None,
            active=bool(membership and membership.is_active),
        )

    def set_portal_password(self, student_id: int, password: str) -> PortalAccountOut:
        """Makes the student's login (username = student code), or gives it a new first
        password. Either way they must choose their own password when they sign in."""
        student = self.get(student_id)
        if not student.is_active:
            raise RuleViolation(f"{student.name} is not an active student")
        user = student.user
        if user is None:
            username = student.code.lower()
            if self.users.get_by_username(username):
                raise Conflict(f"The username {username} is already used")
            user = self.users.add(
                User(name=student.name, username=username, password_hash=hash_password(password))
            )
            student.user = user
        else:
            user.password_hash = hash_password(password)
            user.token_version += 1  # signs them out everywhere
        user.must_change_password = True

        membership = self._portal_membership(student)
        if membership is None:
            role = self.roles.by_key(RoleKey.STUDENT)
            if role is None:
                raise NotFound("The Student role is missing")
            self.members.add(Membership(user=user, role=role, all_branches=False))
        else:
            membership.is_active = True
        self.db.commit()
        return self.portal_account(student.id)

    def close_portal(self, student_id: int) -> PortalAccountOut:
        student = self.get(student_id)
        if membership := self._portal_membership(student):
            membership.is_active = False
            self.db.commit()
        return self.portal_account(student.id)

    def _portal_membership(self, student: Student) -> Membership | None:
        if student.user_id is None:
            return None
        return self.members.first(Membership.user_id == student.user_id)

    def new_qr(self, student_id: int) -> Student:
        """For a lost card: the old card stops working."""
        student = self.get(student_id)
        student.qr_token = new_qr_token()
        self.db.commit()
        return student

    def _home_branch(self, branch_id: int) -> Branch:
        branch = self.branches.get_or_404(branch_id)
        if not branch.is_active:
            raise RuleViolation(f"The {branch.name} branch is inactive")
        return branch

    def _next_code(self) -> str:
        """SAYA-00001, SAYA-00002, ... The institute code makes it unique everywhere."""
        return f"{self.ctx.tenant.code.upper()}-{self.counters.next('student'):05d}"


class EnrollmentService:
    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.db = db
        self.ctx = ctx
        self.enrollments = EnrollmentRepository(db, ctx)
        self.students = StudentRepository(db, ctx)
        self.classes = ClassRepository(db, ctx)

    def list(
        self, class_id: int | None, student_id: int | None, status: EnrollmentStatus | None
    ) -> list[Enrollment]:
        if class_id is None and student_id is None:
            raise RuleViolation("Give a class_id or a student_id")
        if class_id is not None:
            self.classes.get_or_404(class_id)
        return self.enrollments.search(class_id, student_id, status)

    def enroll(self, data: EnrollmentCreate) -> Enrollment:
        cls = self._running_class(data.class_id)
        student = self.students.get_or_404(data.student_id)
        if not student.is_active:
            raise RuleViolation(f"{student.name} is inactive")
        if self.enrollments.active_in_class(student.id, cls.id):
            raise Conflict(f"{student.name} is already in this class")
        if data.card_type != CardType.FULL:
            self._require_cards()

        joined_on = data.joined_on or clock.today()
        enrollment = Enrollment(
            student=student,
            tuition_class=cls,
            branch_id=cls.branch_id,
            joined_on=joined_on,
            start_month=month_of(joined_on),
            card_type=data.card_type,
        )
        self.enrollments.add(enrollment)
        self.db.commit()
        return enrollment

    def update(self, enrollment_id: int, data: EnrollmentUpdate) -> Enrollment:
        enrollment = self._active(enrollment_id)
        changes = data.changes()
        if "card_type" in changes and changes["card_type"] != enrollment.card_type:
            self._require_cards()
            enrollment.card_type = changes["card_type"]
        self.db.commit()
        return enrollment

    def leave(self, enrollment_id: int, data: LeaveIn) -> Enrollment:
        enrollment = self._active(enrollment_id)
        if data.end_month < enrollment.start_month:
            raise RuleViolation("The last month can't be before the student joined")
        enrollment.status = EnrollmentStatus.LEFT
        enrollment.end_month = data.end_month
        self.db.commit()
        return enrollment

    def promote(self, data: PromoteIn) -> PromoteOut:
        """Moves students to the next class (e.g. Grade 6 → Grade 7) and keeps the history.

        Each old enrollment ends the month before start_month and points to the new one.
        Card types carry over.
        """
        source = self.classes.get_or_404(data.from_class_id)
        target = self._running_class(data.to_class_id)
        if target.id == source.id:
            raise RuleViolation("Pick a different class to move the students to")

        moving = self.enrollments.active(source.id, data.enrollment_ids)
        if data.enrollment_ids is not None and len(moving) != len(set(data.enrollment_ids)):
            raise NotFound("Some of these students are not in the class any more")

        last_month = add_months(data.start_month, -1)
        promoted, skipped = 0, []
        for old in moving:
            reason = None
            if old.start_month > last_month:
                reason = "Joined in or after the first month of the new class"
            elif self.enrollments.active_in_class(old.student_id, target.id):
                reason = "Already in the new class"
            if reason:
                skipped.append(
                    SkippedOut(
                        enrollment_id=old.id,
                        student=StudentRef.model_validate(old.student),
                        reason=reason,
                    )
                )
                continue

            new = self.enrollments.add(
                Enrollment(
                    student=old.student,
                    tuition_class=target,
                    branch_id=target.branch_id,
                    joined_on=data.start_month,
                    start_month=data.start_month,
                    card_type=old.card_type,
                )
            )
            old.status = EnrollmentStatus.PROMOTED
            old.end_month = last_month
            old.promoted_to_id = new.id
            self._move_up(old.student, target)
            promoted += 1

        if data.close_old_class and not self.enrollments.active(source.id):
            source.is_active = False
        self.db.commit()
        return PromoteOut(promoted=promoted, skipped=skipped)

    def _running_class(self, class_id: int) -> TuitionClass:
        cls = self.classes.get_or_404(class_id)
        if not cls.is_active:
            raise RuleViolation(f"{cls.title} is inactive")
        return cls

    def _active(self, enrollment_id: int) -> Enrollment:
        enrollment = self.enrollments.get_or_404(enrollment_id)
        if enrollment.status != EnrollmentStatus.ACTIVE:
            raise RuleViolation("The student is no longer in this class")
        return enrollment

    def _require_cards(self) -> None:
        if not self.ctx.has("enrollments.cards"):
            raise Forbidden(
                "You need the 'enrollments.cards' permission to give half or free cards",
                code="permission_denied",
            )

    @staticmethod
    def _move_up(student: Student, target: TuitionClass) -> None:
        """Keep the student's grade and exam year in step with the class they move to."""
        grade = target.level.grade
        if grade is not None and (student.grade is None or student.grade < grade):
            student.grade = grade
        if target.exam_year is not None and student.exam_year is None:
            student.exam_year = target.exam_year
