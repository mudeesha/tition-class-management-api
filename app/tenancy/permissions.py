"""All permission codes live here. `python -m app.cli sync-permissions` copies them to the DB.

Later phases add their own codes (students.*, payments.*, ...) to this list.
"""

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class PermissionDef:
    code: str
    module: str
    description: str


PERMISSIONS: list[PermissionDef] = [
    PermissionDef("settings.view", "setup", "View institute profile and fee settings"),
    PermissionDef("settings.update", "setup", "Change institute profile and fee settings"),
    PermissionDef("branches.view", "setup", "View branches"),
    PermissionDef("branches.manage", "setup", "Create and edit branches"),
    PermissionDef("halls.view", "setup", "View halls"),
    PermissionDef("halls.manage", "setup", "Create, edit and delete halls"),
    PermissionDef("subjects.view", "setup", "View subjects"),
    PermissionDef("subjects.manage", "setup", "Create, edit and delete subjects"),
    PermissionDef("holidays.view", "setup", "View holidays"),
    PermissionDef("holidays.manage", "setup", "Create, edit and delete holidays"),
    PermissionDef("members.view", "users", "View staff accounts"),
    PermissionDef("members.manage", "users", "Add staff accounts and change their access"),
    PermissionDef("roles.view", "users", "View roles and their permissions"),
    PermissionDef("roles.manage", "users", "Create and edit roles"),
    PermissionDef("teachers.view", "teachers", "View teachers"),
    PermissionDef("teachers.manage", "teachers", "Create and edit teachers"),
]

PERMISSION_CODES = frozenset(p.code for p in PERMISSIONS)


class RoleKey(StrEnum):
    """Built-in roles every institute gets. Custom roles have no key."""

    OWNER = "owner"
    BRANCH_MANAGER = "branch_manager"
    STAFF = "staff"
    TEACHER = "teacher"
    STUDENT = "student"


@dataclass(frozen=True)
class DefaultRole:
    key: RoleKey
    name: str
    permissions: frozenset[str]


_ALL_VIEW = frozenset(c for c in PERMISSION_CODES if c.endswith(".view"))

# Owner has every permission implicitly (including ones added later), so it lists none.
DEFAULT_ROLES: list[DefaultRole] = [
    DefaultRole(RoleKey.OWNER, "Owner", frozenset()),
    DefaultRole(
        RoleKey.BRANCH_MANAGER,
        "Branch manager",
        _ALL_VIEW | {"halls.manage", "holidays.manage", "teachers.manage"},
    ),
    DefaultRole(
        RoleKey.STAFF,
        "Staff",
        frozenset(
            {"branches.view", "halls.view", "subjects.view", "holidays.view", "teachers.view"}
        ),
    ),
    DefaultRole(
        RoleKey.TEACHER,
        "Teacher",
        frozenset({"branches.view", "halls.view", "subjects.view", "holidays.view"}),
    ),
    # Portal permissions (tute downloads, own marks, ...) arrive in phase 4.
    DefaultRole(RoleKey.STUDENT, "Student", frozenset()),
]
