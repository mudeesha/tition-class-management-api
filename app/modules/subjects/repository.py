from sqlalchemy import func

from app.common.repository import TenantScopedRepository
from app.modules.subjects.models import Subject, SubjectLevel


class SubjectRepository(TenantScopedRepository[Subject]):
    model = Subject
    label = "Subject"

    def name_taken(
        self, name: str, level: SubjectLevel | None, exclude_id: int | None = None
    ) -> bool:
        where = [
            func.lower(Subject.name) == name.lower(),
            Subject.level.is_(None) if level is None else Subject.level == level,
        ]
        if exclude_id is not None:
            where.append(Subject.id != exclude_id)
        return self.exists(*where)
