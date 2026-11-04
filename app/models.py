"""Imports every model so SQLAlchemy and Alembic see the full schema."""

from app.modules.attendance.models import Attendance, ClassSession
from app.modules.branches.models import Branch, Hall
from app.modules.classes.models import ClassSchedule, TuitionClass
from app.modules.exams.models import Exam, ExamMark, ExamPart
from app.modules.holidays.models import Holiday
from app.modules.institute.models import Counter, InstituteSettings
from app.modules.payments.models import CashHandover, Payment, PaymentItem
from app.modules.platform.models import Plan, Tenant
from app.modules.settlements.models import TeacherPayout
from app.modules.students.models import Enrollment, Student
from app.modules.subjects.models import Subject
from app.modules.teachers.models import Teacher
from app.modules.tutes.models import Tute, TuteIssue
from app.modules.users.models import Membership, Permission, Role, User

__all__ = [
    "Attendance",
    "Branch",
    "CashHandover",
    "ClassSchedule",
    "ClassSession",
    "Counter",
    "Enrollment",
    "Exam",
    "ExamMark",
    "ExamPart",
    "Hall",
    "Holiday",
    "InstituteSettings",
    "Membership",
    "Payment",
    "PaymentItem",
    "Permission",
    "Plan",
    "Role",
    "Student",
    "Subject",
    "Teacher",
    "Tenant",
    "TeacherPayout",
    "TuitionClass",
    "Tute",
    "TuteIssue",
    "User",
]
