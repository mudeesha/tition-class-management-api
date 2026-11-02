"""Institute profile and settings, branches, halls, subjects, holidays, teachers."""

from tests.helpers import error_code, login, make_tenant

# Settings


def test_settings_defaults(owner):
    assert owner.get("/settings").json() == {
        "admission_fee": "0.00",
        "late_join_from_day": 15,
        "late_join_discount_percent": "50.00",
        "warning_until_day": 14,
        "discount_stacking": "both",
        "tute_institute_share_percent": "0.00",
    }


def test_update_settings(owner):
    res = owner.patch(
        "/settings",
        {
            "admission_fee": "1500",
            "discount_stacking": "best_only",
            "tute_institute_share_percent": 20,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["admission_fee"] == "1500.00"
    assert body["discount_stacking"] == "best_only"
    assert body["tute_institute_share_percent"] == "20.00"
    assert body["late_join_from_day"] == 15  # untouched


def test_settings_are_validated(owner):
    assert owner.patch("/settings", {"late_join_discount_percent": 150}).status_code == 422
    assert owner.patch("/settings", {"late_join_from_day": 40}).status_code == 422
    assert owner.patch("/settings", {"admission_fee": None}).status_code == 422
    assert owner.patch("/settings", {"discount_stacking": "half"}).status_code == 422


def test_institute_profile(owner):
    res = owner.patch("/institute", {"phone": "0912234567", "address": "Main St, Galle"})
    assert res.status_code == 200
    body = owner.get("/institute").json()
    assert body["code"] == "saya"
    assert body["phone"] == "0912234567"
    assert body["plan"]["max_branches"] == 1


# Branches


def test_single_branch_plan_cannot_add_a_branch(owner):
    res = owner.post("/branches", {"name": "Galle", "code": "GAL"})
    assert res.status_code == 403
    assert error_code(res) == "plan_limit_reached"


def test_branch_codes_are_unique_and_uppercase(client, db):
    tenant = make_tenant(db, "chain", plan_code="multi_branch")
    owner = login(client, "owner@chain.lk", tenant_id=tenant.id)
    res = owner.post("/branches", {"name": "Galle", "code": "gal"})
    assert res.status_code == 201
    assert res.json()["code"] == "GAL"
    assert owner.post("/branches", {"name": "Galle 2", "code": "GAL"}).status_code == 409


def test_last_active_branch_stays_active(owner):
    main = owner.get("/branches").json()[0]
    res = owner.patch(f"/branches/{main['id']}", {"is_active": False})
    assert res.status_code == 422


def test_reactivating_a_branch_respects_the_limit(client, db, admin):
    tenant = make_tenant(db, "chain", plan_code="multi_branch")  # max 5
    owner = login(client, "owner@chain.lk", tenant_id=tenant.id)
    ids = [
        owner.post("/branches", {"name": f"B{i}", "code": f"B{i}"}).json()["id"] for i in range(4)
    ]
    owner.patch(f"/branches/{ids[0]}", {"is_active": False})
    owner.post("/branches", {"name": "B9", "code": "B9"})  # back to 5 active
    res = owner.patch(f"/branches/{ids[0]}", {"is_active": True})
    assert res.status_code == 403


# Halls


def test_halls(owner):
    main = owner.get("/branches").json()[0]
    res = owner.post("/halls", {"branch_id": main["id"], "name": "Hall 1", "capacity": 120})
    assert res.status_code == 201
    hall = res.json()
    assert hall["branch"]["code"] == "MAIN"

    assert owner.post("/halls", {"branch_id": main["id"], "name": "hall 1"}).status_code == 409
    assert owner.patch(f"/halls/{hall['id']}", {"capacity": 150}).json()["capacity"] == 150
    assert owner.delete(f"/halls/{hall['id']}").status_code == 204
    assert owner.get("/halls").json() == []


# Subjects


def test_subject_names_are_unique_per_level(owner):
    assert owner.post("/subjects", {"name": "Mathematics", "level": "ol"}).status_code == 201
    assert owner.post("/subjects", {"name": "Mathematics", "level": "al"}).status_code == 201
    assert owner.post("/subjects", {"name": "mathematics", "level": "ol"}).status_code == 409
    assert owner.post("/subjects", {"name": "Art"}).status_code == 201
    assert owner.post("/subjects", {"name": "Art"}).status_code == 409

    ol = owner.get("/subjects", params={"level": "ol"}).json()
    assert [s["name"] for s in ol] == ["Mathematics"]


# Holidays


def test_holidays(client, db):
    tenant = make_tenant(db, "chain", plan_code="multi_branch")
    owner = login(client, "owner@chain.lk", tenant_id=tenant.id)
    gal = owner.post("/branches", {"name": "Galle", "code": "GAL"}).json()
    kdy = owner.post("/branches", {"name": "Kandy", "code": "KDY"}).json()

    assert owner.post("/holidays", {"date": "2026-12-25", "name": "Christmas"}).status_code == 201
    res = owner.post(
        "/holidays", {"date": "2026-12-26", "name": "Galle event", "branch_id": gal["id"]}
    )
    assert res.status_code == 201
    owner.post("/holidays", {"date": "2026-12-27", "name": "Kandy event", "branch_id": kdy["id"]})

    # Same day, same branch: rejected. Same day, other branch: fine.
    assert owner.post("/holidays", {"date": "2026-12-25", "name": "Again"}).status_code == 409
    res = owner.post("/holidays", {"date": "2026-12-26", "name": "Again", "branch_id": gal["id"]})
    assert res.status_code == 409

    galle = owner.get("/holidays", params={"branch_id": gal["id"]}).json()
    assert [h["name"] for h in galle] == ["Christmas", "Galle event"]
    assert galle[0]["branch"] is None

    december = owner.get("/holidays", params={"date_from": "2026-12-26", "date_to": "2026-12-31"})
    assert [h["name"] for h in december.json()] == ["Galle event", "Kandy event"]


# Teachers


def test_teachers(owner):
    main = owner.get("/branches").json()[0]
    res = owner.post(
        "/teachers",
        {
            "name": "Sunil Perera",
            "phone": "0771234567",
            "nic": "851234567V",
            "institute_share_percent": "20",
            "branch_ids": [main["id"]],
        },
    )
    assert res.status_code == 201, res.text
    teacher = res.json()
    assert teacher["institute_share_percent"] == "20.00"
    assert [b["code"] for b in teacher["branches"]] == ["MAIN"]

    assert owner.post("/teachers", {"name": "Copy", "nic": "851234567v"}).status_code == 409
    assert (
        owner.post("/teachers", {"name": "Big", "institute_share_percent": 120}).status_code == 422
    )

    owner.post("/teachers", {"name": "Amara Silva"})
    page = owner.get("/teachers", params={"q": "sunil"}).json()
    assert page["total"] == 1
    assert page["items"][0]["id"] == teacher["id"]

    res = owner.patch(f"/teachers/{teacher['id']}", {"is_active": False})
    assert res.json()["is_active"] is False
    assert owner.get("/teachers", params={"is_active": True}).json()["total"] == 1


def test_teacher_limit_of_individual_plan(client, db):
    tenant = make_tenant(db, "solo", plan_code="individual")  # owner already is the 1 teacher
    owner = login(client, "owner@solo.lk", tenant_id=tenant.id)
    res = owner.post("/teachers", {"name": "Second"})
    assert res.status_code == 403
    assert error_code(res) == "plan_limit_reached"


def test_teacher_can_be_linked_to_one_member(owner):
    me = owner.get("/members").json()["items"][0]
    assert owner.post("/teachers", {"name": "A", "membership_id": me["id"]}).status_code == 201
    assert owner.post("/teachers", {"name": "B", "membership_id": me["id"]}).status_code == 409


def test_pagination(owner):
    for i in range(3):
        owner.post("/teachers", {"name": f"Teacher {i}"})
    page = owner.get("/teachers", params={"page": 2, "size": 2}).json()
    assert page["total"] == 3
    assert page["page"] == 2
    assert [t["name"] for t in page["items"]] == ["Teacher 2"]
