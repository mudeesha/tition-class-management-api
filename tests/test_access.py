"""Institute isolation, branch access and permission rules."""

import pytest

from tests.helpers import add_member, error_code, login, make_tenant


@pytest.fixture
def chain(db, client):
    """A multi-branch institute with Galle and Kandy branches and a hall in each."""
    tenant = make_tenant(db, "chain", plan_code="multi_branch")
    owner = login(client, "owner@chain.lk", tenant_id=tenant.id)
    gal = owner.post("/branches", {"name": "Galle", "code": "gal"}).json()
    kdy = owner.post("/branches", {"name": "Kandy", "code": "KDY"}).json()
    owner.post("/halls", {"branch_id": gal["id"], "name": "Hall A"})
    owner.post("/halls", {"branch_id": kdy["id"], "name": "Hall A"})
    return owner, gal, kdy


# Institute isolation


def test_other_institutes_data_is_invisible(client, db, owner):
    subject = owner.post("/subjects", {"name": "Physics", "level": "al"}).json()

    other_tenant = make_tenant(db, "other")
    other = login(client, "owner@other.lk", tenant_id=other_tenant.id)

    assert other.get("/subjects").json() == []
    assert other.get(f"/subjects/{subject['id']}").status_code == 404
    assert other.patch(f"/subjects/{subject['id']}", {"name": "Hacked"}).status_code == 404
    assert other.delete(f"/subjects/{subject['id']}").status_code == 404
    assert owner.get(f"/subjects/{subject['id']}").json()["name"] == "Physics"


def test_cannot_pick_an_institute_you_dont_belong_to(client, db, owner):
    other_tenant = make_tenant(db, "other")
    res = owner.in_tenant(other_tenant.id).get("/branches")
    assert res.status_code == 403


def test_same_codes_are_fine_in_different_institutes(client, db, owner):
    other_tenant = make_tenant(db, "other", plan_code="multi_branch")
    other = login(client, "owner@other.lk", tenant_id=other_tenant.id)
    # Both institutes already have a MAIN branch; adding the same code elsewhere is fine too.
    assert owner.post("/subjects", {"name": "ICT"}).status_code == 201
    assert other.post("/subjects", {"name": "ICT"}).status_code == 201
    assert other.post("/branches", {"name": "Galle", "code": "GAL"}).status_code == 201


# Branch access


def test_branch_limited_member_sees_only_their_branch(db, chain):
    owner, gal, kdy = chain
    staff = add_member(db, owner, "staff@chain.lk", "staff", branch_ids=[gal["id"]])

    assert [b["code"] for b in staff.get("/branches").json()] == ["GAL"]
    assert staff.get(f"/branches/{kdy['id']}").status_code == 404

    halls = staff.get("/halls").json()
    assert [(h["branch"]["code"], h["name"]) for h in halls] == [("GAL", "Hall A")]
    assert staff.get("/halls", params={"branch_id": kdy["id"]}).status_code == 403

    context = staff.get("/auth/context").json()
    assert context["all_branches"] is False
    assert [b["code"] for b in context["branches"]] == ["GAL"]


def test_branch_manager_cannot_add_halls_to_other_branches(db, chain):
    owner, gal, kdy = chain
    manager = add_member(db, owner, "bm@chain.lk", "branch_manager", branch_ids=[gal["id"]])
    assert manager.post("/halls", {"branch_id": gal["id"], "name": "Hall B"}).status_code == 201
    assert manager.post("/halls", {"branch_id": kdy["id"], "name": "Hall B"}).status_code == 404


def test_only_all_branch_members_set_all_branch_holidays(db, chain):
    owner, gal, _ = chain
    manager = add_member(db, owner, "bm@chain.lk", "branch_manager", branch_ids=[gal["id"]])
    res = manager.post("/holidays", {"date": "2026-12-25", "name": "Christmas"})
    assert res.status_code == 403
    res = manager.post(
        "/holidays", {"date": "2026-12-26", "name": "Galle event", "branch_id": gal["id"]}
    )
    assert res.status_code == 201


def test_limited_editor_keeps_teachers_other_branches(db, chain):
    owner, gal, kdy = chain
    teacher = owner.post(
        "/teachers", {"name": "Sunil", "branch_ids": [gal["id"], kdy["id"]]}
    ).json()
    manager = add_member(db, owner, "bm@chain.lk", "branch_manager", branch_ids=[gal["id"]])

    # The manager can't see Kandy, so clearing branches only removes Galle.
    res = manager.patch(f"/teachers/{teacher['id']}", {"branch_ids": []})
    assert res.status_code == 200
    assert [b["code"] for b in owner.get(f"/teachers/{teacher['id']}").json()["branches"]] == [
        "KDY"
    ]
    # And now the teacher is out of the manager's sight.
    assert manager.get(f"/teachers/{teacher['id']}").status_code == 404


# Permissions


def test_staff_can_view_but_not_manage(db, owner):
    staff = add_member(db, owner, "staff@saya.lk", "staff")
    assert staff.get("/subjects").status_code == 200
    res = staff.post("/subjects", {"name": "Maths"})
    assert res.status_code == 403
    assert error_code(res) == "permission_denied"
    assert staff.get("/settings").status_code == 403


def test_extra_permissions_can_be_given_directly(db, owner):
    staff = add_member(db, owner, "staff@saya.lk", "staff", permission_codes=["subjects.manage"])
    assert staff.post("/subjects", {"name": "Maths"}).status_code == 201
    assert "subjects.manage" in staff.get("/auth/context").json()["permissions"]


def test_cannot_grant_permissions_you_dont_have(db, owner):
    roles = {r["key"]: r["id"] for r in owner.get("/roles").json()}
    manager = add_member(
        db, owner, "bm@saya.lk", "branch_manager", permission_codes=["members.manage"]
    )

    def add(**body):
        return manager.post(
            "/members",
            {"name": "X", "email": "x@saya.lk", "password": "password123", **body},
        )

    assert add(role_id=roles["staff"], permission_codes=["roles.manage"]).status_code == 403
    assert add(role_id=roles["owner"]).status_code == 403
    assert add(role_id=roles["staff"], all_branches=True).status_code == 403
    assert add(role_id=roles["staff"]).status_code == 201


def test_cannot_add_students_as_members(owner):
    roles = {r["key"]: r["id"] for r in owner.get("/roles").json()}
    res = owner.post(
        "/members",
        {"name": "S", "username": "st001", "password": "password123", "role_id": roles["student"]},
    )
    assert res.status_code == 422


def test_owner_cannot_lock_themselves_out(owner):
    me = owner.get("/members").json()["items"][0]
    res = owner.patch(f"/members/{me['id']}", {"is_active": False})
    assert res.status_code == 422


def test_last_owner_cannot_be_demoted(db, owner):
    roles = {r["key"]: r["id"] for r in owner.get("/roles").json()}
    second = add_member(db, owner, "owner2@saya.lk", "owner")
    members = {m["user"]["email"]: m["id"] for m in owner.get("/members").json()["items"]}

    # With two owners, one can demote the other...
    res = second.patch(f"/members/{members['owner@saya.lk']}", {"role_id": roles["staff"]})
    assert res.status_code == 200
    # ...but the remaining owner can't demote themselves away.
    res = second.patch(f"/members/{members['owner2@saya.lk']}", {"role_id": roles["staff"]})
    assert res.status_code == 422


def test_existing_user_joins_as_member_with_their_own_password(client, db, owner):
    other_tenant = make_tenant(db, "other")
    roles = {r["key"]: r["id"] for r in owner.get("/roles").json()}
    res = owner.post(
        "/members", {"name": "Other", "email": "owner@other.lk", "role_id": roles["staff"]}
    )
    assert res.status_code == 201
    me = login(client, "owner@other.lk").get("/auth/me").json()
    assert {m["tenant_code"] for m in me["memberships"]} == {"saya", "other"}
    assert other_tenant  # still owner there

    res = owner.post(
        "/members", {"name": "Other", "email": "owner@other.lk", "role_id": roles["staff"]}
    )
    assert res.status_code == 409


def test_user_limit_of_the_plan(db, client):
    tenant = make_tenant(db, "solo", plan_code="individual")  # max 3 users
    owner = login(client, "owner@solo.lk", tenant_id=tenant.id)
    add_member(db, owner, "a@solo.lk", "staff")
    add_member(db, owner, "b@solo.lk", "staff")
    roles = {r["key"]: r["id"] for r in owner.get("/roles").json()}
    res = owner.post(
        "/members",
        {"name": "C", "email": "c@solo.lk", "password": "password123", "role_id": roles["staff"]},
    )
    assert res.status_code == 403
    assert error_code(res) == "plan_limit_reached"


# Roles


def test_custom_role_lifecycle(db, owner):
    res = owner.post("/roles", {"name": "Cashier", "permission_codes": ["branches.view"]})
    assert res.status_code == 201
    role = res.json()
    assert role["permission_codes"] == ["branches.view"]

    res = owner.patch(
        f"/roles/{role['id']}", {"permission_codes": ["branches.view", "teachers.view"]}
    )
    assert res.json()["permission_codes"] == ["branches.view", "teachers.view"]

    assert owner.post("/roles", {"name": "cashier"}).status_code == 409
    assert owner.delete(f"/roles/{role['id']}").status_code == 204


def test_role_in_use_cannot_be_deleted(db, owner):
    role = owner.post("/roles", {"name": "Cashier"}).json()
    roles = {r["name"]: r for r in owner.get("/roles").json()}
    assert roles["Cashier"]["id"] == role["id"]
    owner.post(
        "/members",
        {"name": "C", "email": "c@saya.lk", "password": "password123", "role_id": role["id"]},
    )
    assert owner.delete(f"/roles/{role['id']}").status_code == 409


def test_built_in_roles_are_protected(owner):
    roles = {r["key"]: r for r in owner.get("/roles").json()}
    assert (
        owner.patch(f"/roles/{roles['owner']['id']}", {"permission_codes": []}).status_code == 422
    )
    assert owner.patch(f"/roles/{roles['staff']['id']}", {"name": "Helpers"}).status_code == 422
    assert owner.delete(f"/roles/{roles['staff']['id']}").status_code == 422
    # Their permissions can still be changed.
    res = owner.patch(f"/roles/{roles['staff']['id']}", {"permission_codes": ["subjects.view"]})
    assert res.status_code == 200


def test_unknown_permission_code(owner):
    res = owner.post("/roles", {"name": "Odd", "permission_codes": ["nope.nope"]})
    assert res.status_code == 422


def test_permission_list(owner):
    codes = {p["code"] for p in owner.get("/permissions").json()}
    assert {"branches.manage", "members.manage", "teachers.view"} <= codes
