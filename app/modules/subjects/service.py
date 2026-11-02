from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import Conflict
from app.modules.subjects.models import Subject, SubjectLevel
from app.modules.subjects.repository import SubjectRepository
from app.modules.subjects.schemas import SubjectCreate, SubjectUpdate
from app.tenancy.context import TenantContext


class SubjectService:
    def __init__(self, db: Session, ctx: TenantContext) -> None:
        self.db = db
        self.subjects = SubjectRepository(db, ctx)

    def list(self, level: SubjectLevel | None = None) -> list[Subject]:
        where = [Subject.level == level] if level else []
        return self.subjects.find(*where, order_by=[Subject.name, Subject.level])

    def get(self, subject_id: int) -> Subject:
        return self.subjects.get_or_404(subject_id)

    def create(self, data: SubjectCreate) -> Subject:
        if self.subjects.name_taken(data.name, data.level):
            raise Conflict(f"{data.name} already exists for this level")
        subject = self.subjects.add(Subject(**data.model_dump()))
        self.db.commit()
        return subject

    def update(self, subject_id: int, data: SubjectUpdate) -> Subject:
        subject = self.get(subject_id)
        changes = data.changes()
        name = changes.get("name", subject.name)
        level = changes.get("level", subject.level)
        if self.subjects.name_taken(name, level, subject.id):
            raise Conflict(f"{name} already exists for this level")
        for field, value in changes.items():
            setattr(subject, field, value)
        self.db.commit()
        return subject

    def delete(self, subject_id: int) -> None:
        self.subjects.delete(self.get(subject_id))
        self.db.commit()
