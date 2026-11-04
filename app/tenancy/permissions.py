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
    PermissionDef("classes.view", "classes", "View classes and the timetable"),
    PermissionDef("classes.manage", "classes", "Create and edit classes and their schedules"),
    PermissionDef("students.view", "students", "View students"),
    PermissionDef("students.manage", "students", "Register and edit students"),
    PermissionDef(
        "enrollments.manage", "students", "Add students to classes, remove and promote them"
    ),
    PermissionDef("enrollments.cards", "students", "Give half and free cards"),
    PermissionDef("payments.view", "payments", "View receipts and what students owe"),
    PermissionDef("payments.create", "payments", "Collect fees and print receipts"),
    PermissionDef("payments.void", "payments", "Void receipts"),
    PermissionDef("cash.receive", "payments", "Take over cash from the people who collected it"),
    PermissionDef("attendance.view", "attendance", "View class days and attendance"),
    PermissionDef("attendance.mark", "attendance", "Scan cards and mark attendance"),
    PermissionDef("tutes.view", "tutes", "View tutes and who got them"),
    PermissionDef("tutes.manage", "tutes", "Add tutes and upload soft copies"),
    PermissionDef("tutes.issue", "tutes", "Tick hard copies as given"),
    PermissionDef("exams.view", "exams", "View exams, marks and ranks"),
    PermissionDef("exams.manage", "exams", "Create exams and enter marks"),
    PermissionDef("settlements.view", "settlements", "View teacher settlements"),
    PermissionDef("settlements.pay", "settlements", "Record and void teacher payouts"),
    PermissionDef("reports.view", "reports", "View reports (fees owed, collections, attendance)"),
    # For the Student role: what students see about themselves in the portal.
    PermissionDef("portal.payments", "portal", "See their own fees and receipts"),
    PermissionDef("portal.attendance", "portal", "See their own attendance"),
    PermissionDef("portal.tutes", "portal", "Download the tutes they may have"),
    PermissionDef("portal.marks", "portal", "See their own published marks and ranks"),
]

PORTAL_CODES = frozenset(p.code for p in PERMISSIONS if p.module == "portal")

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
        # Settlements cover every branch, so they stay with the owner unless given.
        (_ALL_VIEW - {"settlements.view"})
        | {
            "halls.manage",
            "holidays.manage",
            "teachers.manage",
            "classes.manage",
            "students.manage",
            "enrollments.manage",
            "enrollments.cards",
            "payments.create",
            "payments.void",
            "cash.receive",
            "attendance.mark",
            "tutes.manage",
            "tutes.issue",
            "exams.manage",
        },
    ),
    DefaultRole(
        RoleKey.STAFF,
        "Staff",
        frozenset(
            {
                "branches.view",
                "halls.view",
                "subjects.view",
                "holidays.view",
                "teachers.view",
                "classes.view",
                "students.view",
                "students.manage",
                "enrollments.manage",
                "payments.view",
                "payments.create",
                "attendance.view",
                "attendance.mark",
                "tutes.view",
                "tutes.issue",
                "exams.view",
            }
        ),
    ),
    DefaultRole(
        RoleKey.TEACHER,
        "Teacher",
        frozenset(
            {
                "branches.view",
                "halls.view",
                "subjects.view",
                "holidays.view",
                "classes.view",
                "students.view",
                "attendance.view",
                "attendance.mark",
                "tutes.view",
                "tutes.manage",
                "tutes.issue",
                "exams.view",
                "exams.manage",
            }
        ),
    ),
    DefaultRole(RoleKey.STUDENT, "Student", PORTAL_CODES),
]
