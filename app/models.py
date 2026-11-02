"""Imports every model so SQLAlchemy and Alembic see the full schema."""

from app.modules.branches.models import Branch, Hall
from app.modules.holidays.models import Holiday
from app.modules.institute.models import InstituteSettings
from app.modules.platform.models import Plan, Tenant
from app.modules.subjects.models import Subject
from app.modules.teachers.models import Teacher
from app.modules.users.models import Membership, Permission, Role, User

__all__ = [
    "Branch",
    "Hall",
    "Holiday",
    "InstituteSettings",
    "Membership",
    "Permission",
    "Plan",
    "Role",
    "Subject",
    "Teacher",
    "Tenant",
    "User",
]
