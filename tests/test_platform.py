from app.modules.platform.models import TenantStatus
from app.modules.users.repository import UserRepository
from tests.helpers import PASSWORD, error_code, login, make_tenant


def _plan_id(admin, code):
    return next(p["id"] for p in admin.get("/platform/plans").json() if p["code"] == code)


def _new_tenant(admin, code, plan_code="institute", email=None):
    return admin.post(
        "/platform/tenants",
        {
            "code": code,
            "name": f"{code} institute",
            "plan_id": _plan_id(admin, plan_code),
            "owner": {"name": "Kamal", "email": email or f"kamal@{code}.lk", "password": PASSWORD},
        },
    )


def test_only_platform_admins_can_use_platform_endpoints(owner):
    res = owner.get("/platform/tenants")
    assert res.status_code == 403


def test_default_plans_are_seeded(admin):
    codes = {p["code"] for p in admin.get("/platform/plans").json()}
    assert codes == {"individual", "institute", "multi_branch"}


def test_creating_a_tenant_sets_everything_up(client, db, admin):
    res = _new_tenant(admin, "nenasa")
    assert res.status_code == 201, res.text
    tenant = res.json()
    assert tenant["status"] == "trial"
    assert tenant["plan"]["code"] == "institute"

    # The owner must set their own password before working in the institute.
    owner_user = UserRepository(db).get_by_email("kamal@nenasa.lk")
    assert owner_user.must_change_password is True
    owner_user.must_change_password = False
    db.commit()

    owner = login(client, "kamal@nenasa.lk", tenant_id=tenant["id"])
    roles = owner.get("/roles").json()
    assert {r["key"] for r in roles} == {
        "owner",
        "branch_manager",
        "staff",
        "teacher",
        "student",
    }
    assert all(r["is_system"] for r in roles)
    assert [b["code"] for b in owner.get("/branches").json()] == ["MAIN"]
    assert owner.get("/settings").json()["late_join_from_day"] == 15
    # An institute owner isn't automatically a teacher.
    assert owner.get("/teachers").json()["total"] == 0


def test_individual_teacher_gets_a_teacher_profile(client, db):
    tenant = make_tenant(db, "ruwan", plan_code="individual")
    owner = login(client, "owner@ruwan.lk", tenant_id=tenant.id)
    teachers = owner.get("/teachers").json()["items"]
    assert len(teachers) == 1
    assert teachers[0]["name"] == "Owner ruwan"
    assert [b["code"] for b in teachers[0]["branches"]] == ["MAIN"]
    assert teachers[0]["membership_id"] is not None


def test_existing_user_can_own_a_second_institute(client, db, admin, saya):
    res = _new_tenant(admin, "second", email="owner@saya.lk")
    assert res.status_code == 201
    # Their password is unchanged and they now see both institutes.
    me = login(client, "owner@saya.lk").get("/auth/me").json()
    assert {m["tenant_code"] for m in me["memberships"]} == {"saya", "second"}


def test_tenant_code_must_be_unique(admin, saya):
    res = _new_tenant(admin, "saya")
    assert res.status_code == 409


def test_tenant_code_format_is_checked(admin):
    res = _new_tenant(admin, "Bad Code!")
    assert res.status_code == 422
    assert error_code(res) == "validation_error"


def test_suspended_tenant_blocks_its_members(admin, owner, saya):
    res = admin.patch(f"/platform/tenants/{saya.id}", {"status": TenantStatus.SUSPENDED})
    assert res.status_code == 200
    res = owner.get("/branches")
    assert res.status_code == 403
    assert error_code(res) == "tenant_suspended"


def test_admin_can_change_a_tenants_plan(admin, saya):
    res = admin.patch(f"/platform/tenants/{saya.id}", {"plan_id": _plan_id(admin, "multi_branch")})
    assert res.status_code == 200
    assert res.json()["plan"]["code"] == "multi_branch"


def test_tenant_search(admin, saya):
    res = admin.get("/platform/tenants", params={"q": "say"})
    assert [t["code"] for t in res.json()["items"]] == ["saya"]
