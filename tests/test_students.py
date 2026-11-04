"""Student registration, enrollments, half/free cards, leaving and promotion."""

from app.modules.platform.repository import PlanRepository
from tests.helpers import add_member, error_code, login, make_tenant, new_class, new_student


def enroll(api, student, cls, **fields):
    return api.post("/enrollments", {"student_id": student["id"], "class_id": cls["id"], **fields})


# Registration


def test_register_students_with_codes_and_cards(campus):
    first = new_student(
        campus.owner,
        campus.gal["id"],
        school="Richmond College",
        grade=10,
        guardian_name="Nimal Perera",
        guardian_phone="0771234567",
    )
    assert first["code"] == "CHAIN-00001"
    assert first["home_branch"]["code"] == "GAL"
    assert len(first["qr_token"]) >= 32
    assert first["is_active"] is True

    second = new_student(campus.owner, campus.kdy["id"], name="Dilini")
    assert second["code"] == "CHAIN-00002"
    assert second["qr_token"] != first["qr_token"]


def test_codes_are_counted_per_institute(client, db, campus):
    new_student(campus.owner, campus.gal["id"])
    other_tenant = make_tenant(db, "saya")
    other = login(client, "owner@saya.lk", tenant_id=other_tenant.id)
    main = other.get("/branches").json()[0]
    assert new_student(other, main["id"])["code"] == "SAYA-00001"


def test_new_card_replaces_the_qr_code(campus):
    student = new_student(campus.owner, campus.gal["id"])
    res = campus.owner.post(f"/students/{student['id']}/new-card")
    assert res.status_code == 200
    assert res.json()["qr_token"] != student["qr_token"]
    assert res.json()["code"] == student["code"]


def test_student_limit_of_the_plan(db, campus):
    PlanRepository(db).by_code("multi_branch").max_students = 1
    db.flush()
    new_student(campus.owner, campus.gal["id"])
    res = campus.owner.post("/students", {"name": "Two", "home_branch_id": campus.gal["id"]})
    assert res.status_code == 403
    assert error_code(res) == "plan_limit_reached"


def test_search_students(campus):
    kasun = new_student(campus.owner, campus.gal["id"], phone="0711111111")
    new_student(campus.owner, campus.kdy["id"], name="Dilini Silva", guardian_phone="0722222222")

    def names(**params):
        return [s["name"] for s in campus.owner.get("/students", params=params).json()["items"]]

    assert names(q="kasun") == ["Kasun Perera"]
    assert names(q=kasun["code"].lower()) == ["Kasun Perera"]
    assert names(q="0711") == ["Kasun Perera"]
    assert names(q="0722") == ["Dilini Silva"]
    assert names(branch_id=campus.kdy["id"]) == ["Dilini Silva"]

    # A Galle student attending a Kandy class shows up for Kandy too.
    kandy_class = new_class(campus, branch_id=campus.kdy["id"], hall_id=None)
    enroll(campus.owner, kasun, kandy_class)
    assert names(branch_id=campus.kdy["id"]) == ["Dilini Silva", "Kasun Perera"]
    assert names(class_id=kandy_class["id"]) == ["Kasun Perera"]


def test_edit_student(campus):
    student = new_student(campus.owner, campus.gal["id"])
    res = campus.owner.patch(
        f"/students/{student['id']}", {"grade": 11, "home_branch_id": campus.kdy["id"]}
    )
    assert res.status_code == 200
    assert res.json()["grade"] == 11
    assert res.json()["home_branch"]["code"] == "KDY"
    assert campus.owner.patch(f"/students/{student['id']}", {"grade": 14}).status_code == 422
    assert campus.owner.patch(f"/students/{student['id']}", {"name": None}).status_code == 422


# Enrollments


def test_enroll_and_list_the_class(campus):
    cls = new_class(campus)
    student = new_student(campus.owner, campus.gal["id"])

    res = enroll(campus.owner, student, cls, joined_on="2026-11-20")
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["start_month"] == "2026-11"
    assert body["end_month"] is None
    assert body["card_type"] == "full"
    assert body["status"] == "active"
    assert body["tuition_class"]["title"] == "Grade 10 Mathematics – Class 1"

    assert enroll(campus.owner, student, cls).status_code == 409
    assert campus.owner.get(f"/classes/{cls['id']}").json()["student_count"] == 1

    roster = campus.owner.get("/enrollments", params={"class_id": cls["id"]}).json()
    assert [e["student"]["name"] for e in roster] == ["Kasun Perera"]
    profile = campus.owner.get(f"/students/{student['id']}").json()
    assert [e["tuition_class"]["id"] for e in profile["enrollments"]] == [cls["id"]]


def test_half_and_free_cards_need_their_own_permission(db, campus):
    cls = new_class(campus)
    student = new_student(campus.owner, campus.gal["id"])
    staff = add_member(db, campus.owner, "staff@chain.lk", "staff", branch_ids=[campus.gal["id"]])

    res = enroll(staff, student, cls, card_type="half")
    assert res.status_code == 403
    assert error_code(res) == "permission_denied"

    enrollment = enroll(staff, student, cls).json()
    assert staff.patch(f"/enrollments/{enrollment['id']}", {"card_type": "free"}).status_code == 403
    res = campus.owner.patch(f"/enrollments/{enrollment['id']}", {"card_type": "free"})
    assert res.json()["card_type"] == "free"


def test_leave_and_join_again(campus):
    cls = new_class(campus)
    student = new_student(campus.owner, campus.gal["id"])
    first = enroll(campus.owner, student, cls, joined_on="2026-03-05").json()

    leave = f"/enrollments/{first['id']}/leave"
    assert campus.owner.post(leave, {"end_month": "2026-02"}).status_code == 422
    assert campus.owner.post(leave, {"end_month": "2026/06"}).status_code == 422
    res = campus.owner.post(leave, {"end_month": "2026-06"})
    assert res.json()["status"] == "left"
    assert res.json()["end_month"] == "2026-06"
    assert campus.owner.post(leave, {"end_month": "2026-07"}).status_code == 422
    assert campus.owner.get(f"/classes/{cls['id']}").json()["student_count"] == 0

    again = enroll(campus.owner, student, cls, joined_on="2026-09-01")
    assert again.status_code == 201
    history = campus.owner.get(f"/students/{student['id']}").json()["enrollments"]
    assert [(e["status"], e["start_month"]) for e in history] == [
        ("active", "2026-09"),
        ("left", "2026-03"),
    ]


def test_inactive_classes_and_students_cant_be_joined(campus):
    cls = new_class(campus)
    student = new_student(campus.owner, campus.gal["id"])
    campus.owner.patch(f"/students/{student['id']}", {"is_active": False})
    assert enroll(campus.owner, student, cls).status_code == 422

    campus.owner.patch(f"/students/{student['id']}", {"is_active": True})
    campus.owner.patch(f"/classes/{cls['id']}", {"is_active": False})
    assert enroll(campus.owner, student, cls).status_code == 422


def test_branch_staff_see_only_their_branch_classes(db, campus):
    galle = new_class(campus)
    kandy = new_class(campus, branch_id=campus.kdy["id"], hall_id=None)
    student = new_student(campus.owner, campus.gal["id"])
    enroll(campus.owner, student, galle)
    enroll(campus.owner, student, kandy)
    staff = add_member(db, campus.owner, "staff@chain.lk", "staff", branch_ids=[campus.gal["id"]])

    # The student belongs to the institute, but Kandy's class is hidden from Galle staff.
    profile = staff.get(f"/students/{student['id']}").json()
    assert [e["tuition_class"]["id"] for e in profile["enrollments"]] == [galle["id"]]
    other = new_student(campus.owner, campus.kdy["id"], name="Dilini")
    assert enroll(staff, other, kandy).status_code == 404
    assert enroll(staff, other, galle).status_code == 201
    # And they can't register students into a branch they don't work in.
    res = staff.post("/students", {"name": "X", "home_branch_id": campus.kdy["id"]})
    assert res.status_code == 404


# Promotion


def test_promote_a_class_to_the_next_grade(campus):
    grade_10 = new_class(campus)
    grade_11 = new_class(campus, level="grade_11", hall_id=campus.hall_b["id"])
    kasun = new_student(campus.owner, campus.gal["id"], grade=10)
    dilini = new_student(campus.owner, campus.gal["id"], name="Dilini", grade=10)
    late = new_student(campus.owner, campus.gal["id"], name="Late joiner")
    already = new_student(campus.owner, campus.gal["id"], name="Already there")

    half = enroll(campus.owner, kasun, grade_10, joined_on="2026-02-01", card_type="half").json()
    enroll(campus.owner, dilini, grade_10, joined_on="2026-02-10")
    enroll(campus.owner, late, grade_10, joined_on="2027-01-05")
    enroll(campus.owner, already, grade_10, joined_on="2026-02-01")
    enroll(campus.owner, already, grade_11, joined_on="2026-12-01")

    res = campus.owner.post(
        "/enrollments/promote",
        {"from_class_id": grade_10["id"], "to_class_id": grade_11["id"], "start_month": "2027-01"},
    )
    assert res.status_code == 200, res.text
    result = res.json()
    assert result["promoted"] == 2
    assert sorted((s["student"]["name"], s["reason"]) for s in result["skipped"]) == [
        ("Already there", "Already in the new class"),
        ("Late joiner", "Joined in or after the first month of the new class"),
    ]

    history = campus.owner.get(f"/students/{kasun['id']}").json()
    assert history["grade"] == 11
    current, old = history["enrollments"]
    assert (current["tuition_class"]["id"], current["status"]) == (grade_11["id"], "active")
    assert current["start_month"] == "2027-01"
    assert current["card_type"] == "half"  # cards carry over
    assert old["id"] == half["id"]
    assert (old["status"], old["end_month"]) == ("promoted", "2026-12")
    assert old["promoted_to_id"] == current["id"]


def test_promote_some_students_and_close_the_class(campus):
    old_class = new_class(campus, level="grade_6")
    new_class_ = new_class(campus, level="grade_7", hall_id=campus.hall_b["id"])
    a = new_student(campus.owner, campus.gal["id"], name="A")
    b = new_student(campus.owner, campus.gal["id"], name="B")
    ea = enroll(campus.owner, a, old_class, joined_on="2026-01-01").json()
    eb = enroll(campus.owner, b, old_class, joined_on="2026-01-01").json()

    body = {
        "from_class_id": old_class["id"],
        "to_class_id": new_class_["id"],
        "start_month": "2027-01",
        "close_old_class": True,
    }
    res = campus.owner.post("/enrollments/promote", {**body, "enrollment_ids": [ea["id"]]})
    assert res.json()["promoted"] == 1
    # B is still there, so the old class stays open.
    assert campus.owner.get(f"/classes/{old_class['id']}").json()["is_active"] is True

    res = campus.owner.post("/enrollments/promote", {**body, "enrollment_ids": [eb["id"]]})
    assert res.json()["promoted"] == 1
    assert campus.owner.get(f"/classes/{old_class['id']}").json()["is_active"] is False

    res = campus.owner.post("/enrollments/promote", {**body, "enrollment_ids": [ea["id"]]})
    assert res.status_code == 404


def test_promote_needs_a_different_running_class(campus):
    cls = new_class(campus)
    body = {"from_class_id": cls["id"], "to_class_id": cls["id"], "start_month": "2027-01"}
    assert campus.owner.post("/enrollments/promote", body).status_code == 422
