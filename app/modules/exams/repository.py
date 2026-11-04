import datetime as dt

from sqlalchemy import Select, exists, func

from app.common.repository import TenantScopedRepository
from app.modules.classes.models import TuitionClass
from app.modules.exams.models import Exam, ExamMark, exam_classes


class ExamRepository(TenantScopedRepository[Exam]):
    """Members limited to some branches see exams of classes in one of them."""

    model = Exam
    label = "Exam"

    def query(self) -> Select[tuple[Exam]]:
        stmt = super().query()
        if not self.ctx.all_branches:
            stmt = stmt.where(
                exists()
                .where(exam_classes.c.exam_id == Exam.id)
                .where(exam_classes.c.class_id == TuitionClass.id)
                .where(TuitionClass.branch_id.in_(self.ctx.branch_ids))
            )
        return stmt

    def search(
        self,
        q: str | None,
        class_id: int | None,
        teacher_id: int | None,
        subject_id: int | None,
        date_from: dt.date | None,
        date_to: dt.date | None,
    ) -> Select[tuple[Exam]]:
        stmt = self.query()
        if q:
            stmt = stmt.where(func.lower(Exam.title).like(f"%{q.lower()}%"))
        if class_id is not None:
            stmt = stmt.where(self._for([class_id]))
        if teacher_id is not None:
            stmt = stmt.where(Exam.teacher_id == teacher_id)
        if subject_id is not None:
            stmt = stmt.where(Exam.subject_id == subject_id)
        if date_from is not None:
            stmt = stmt.where(Exam.date >= date_from)
        if date_to is not None:
            stmt = stmt.where(Exam.date <= date_to)
        return stmt.order_by(Exam.date.desc(), Exam.id.desc())

    def published_for(self, class_ids: list[int]) -> list[Exam]:
        if not class_ids:
            return []
        return self.find(
            Exam.published.is_(True), self._for(class_ids), order_by=[Exam.date.desc()]
        )

    @staticmethod
    def _for(class_ids: list[int]):
        return exists().where(
            exam_classes.c.exam_id == Exam.id, exam_classes.c.class_id.in_(class_ids)
        )


class MarkRepository(TenantScopedRepository[ExamMark]):
    model = ExamMark
    label = "Marks"

    def for_exam(self, exam_id: int) -> list[ExamMark]:
        return self.find(ExamMark.exam_id == exam_id)

    def any_for_part(self, part_id: int) -> bool:
        return self.exists(ExamMark.part_id == part_id)

    def highest_for_part(self, part_id: int):
        stmt = (
            self.query()
            .with_only_columns(func.max(ExamMark.marks))
            .where(ExamMark.part_id == part_id)
        )
        return self.db.scalar(stmt)
