from dataclasses import dataclass

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.platform.models import Tenant, TenantStatus
from app.modules.platform.repository import PlanRepository
from app.modules.platform.schemas import OwnerIn, TenantCreate
from app.modules.platform.service import PlatformService
from app.modules.users.repository import UserRepository

PASSWORD = "password123"


@dataclass
class Api:
    """A signed-in test client working in one institute."""

    client: TestClient
    token: str
    tenant_id: int | None = None

    @property
    def headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.token}"}
        if self.tenant_id is not None:
            headers["X-Tenant-ID"] = str(self.tenant_id)
        return headers

    def get(self, url: str, **kw):
        return self.client.get(f"/api/v1{url}", headers=self.headers, **kw)

    def post(self, url: str, json=None, **kw):
        return self.client.post(f"/api/v1{url}", json=json, headers=self.headers, **kw)

    def patch(self, url: str, json=None, **kw):
        return self.client.patch(f"/api/v1{url}", json=json, headers=self.headers, **kw)

    def put(self, url: str, json=None, **kw):
        return self.client.put(f"/api/v1{url}", json=json, headers=self.headers, **kw)

    def delete(self, url: str, **kw):
        return self.client.delete(f"/api/v1{url}", headers=self.headers, **kw)

    def in_tenant(self, tenant_id: int) -> "Api":
        return Api(self.client, self.token, tenant_id)


def login(client: TestClient, login: str, password: str = PASSWORD, tenant_id=None) -> Api:
    res = client.post("/api/v1/auth/login", json={"login": login, "password": password})
    assert res.status_code == 200, res.text
    return Api(client, res.json()["access_token"], tenant_id)


def skip_password_change(db: Session, login: str) -> None:
    user = UserRepository(db).get_by_login(login)
    user.must_change_password = False
    db.commit()


def make_tenant(
    db: Session, code: str, plan_code: str = "institute", owner_email: str | None = None
) -> Tenant:
    owner_email = owner_email or f"owner@{code}.lk"
    plan = PlanRepository(db).by_code(plan_code)
    tenant = PlatformService(db).create_tenant(
        TenantCreate(
            code=code,
            name=f"{code.title()} Institute",
            plan_id=plan.id,
            status=TenantStatus.ACTIVE,
            owner=OwnerIn(name=f"Owner {code}", email=owner_email, password=PASSWORD),
        )
    )
    skip_password_change(db, owner_email)
    return tenant


def add_member(
    db: Session,
    owner: Api,
    email: str,
    role_key: str,
    *,
    branch_ids: list[int] = (),
    all_branches: bool = False,
    permission_codes: list[str] = (),
) -> Api:
    """Owner adds a staff member, who then signs in."""
    roles = {r["key"]: r["id"] for r in owner.get("/roles").json()}
    res = owner.post(
        "/members",
        {
            "name": email.split("@")[0],
            "email": email,
            "password": PASSWORD,
            "role_id": roles[role_key],
            "all_branches": all_branches,
            "branch_ids": list(branch_ids),
            "permission_codes": list(permission_codes),
        },
    )
    assert res.status_code == 201, res.text
    skip_password_change(db, email)
    return login(owner.client, email, tenant_id=owner.tenant_id)


def error_code(res) -> str:
    return res.json()["error"]["code"]


def new_class(campus, **fields) -> dict:
    """A Grade 10 maths class with Sunil in Galle, Hall A, unless `fields` say otherwise."""
    body = {
        "branch_id": campus.gal["id"],
        "subject_id": campus.maths["id"],
        "teacher_id": campus.sunil["id"],
        "level": "grade_10",
        "monthly_fee": "2000",
        "hall_id": campus.hall_a["id"],
        **fields,
    }
    res = campus.owner.post("/classes", body)
    assert res.status_code == 201, res.text
    return res.json()


def new_student(api: Api, branch_id: int, name: str = "Kasun Perera", **fields) -> dict:
    res = api.post("/students", {"name": name, "home_branch_id": branch_id, **fields})
    assert res.status_code == 201, res.text
    return res.json()


def slot(weekday: int, start: str, end: str, **fields) -> dict:
    return {"weekday": weekday, "start_time": start, "end_time": end, **fields}


def future_month(months_ahead: int = 2):
    """The first day of a month after today, so class days aren't "before the class existed"."""
    from datetime import date

    from app.common.schemas import add_months, month_of

    return add_months(month_of(date.today()), months_ahead)


def ym(day) -> str:
    return day.strftime("%Y-%m")


def enroll(api: Api, student: dict, cls: dict, **fields):
    return api.post("/enrollments", {"student_id": student["id"], "class_id": cls["id"], **fields})
