"""Classes, weekly schedules and the hall and teacher clash checks."""

from tests.helpers import add_member, error_code, new_class, slot

SATURDAY = 6


def test_create_class(campus):
    cls = new_class(campus)
    assert cls["title"] == "Grade 10 Mathematics – Class 1"
    assert cls["monthly_fee"] == "2000.00"
    assert cls["branch"]["code"] == "GAL"
    assert cls["teacher"]["name"] == "Sunil"
    assert cls["hall"]["name"] == "Hall A"
    assert cls["schedules"] == []
    assert cls["student_count"] == 0


def test_al_classes_need_an_exam_year(campus):
    res = campus.owner.post(
        "/classes",
        {
            "branch_id": campus.gal["id"],
            "subject_id": campus.physics["id"],
            "teacher_id": campus.sunil["id"],
            "level": "al",
            "monthly_fee": "2500",
        },
    )
    assert res.status_code == 422
    assert res.json()["error"]["details"][0]["loc"] == ["body", "exam_year"]

    cls = new_class(campus, subject_id=campus.physics["id"], level="al", exam_year=2027)
    assert cls["title"] == "2027 A/L Physics – Class 1"

    plain = new_class(campus)
    res = campus.owner.patch(f"/classes/{plain['id']}", {"level": "al"})
    assert res.status_code == 422


def test_teacher_must_work_at_the_branch(campus):
    res = campus.owner.post(
        "/classes",
        {
            "branch_id": campus.kdy["id"],
            "subject_id": campus.maths["id"],
            "teacher_id": campus.amara["id"],
            "level": "grade_9",
            "monthly_fee": "1500",
        },
    )
    assert res.status_code == 422
    assert "Amara isn't assigned to the Kandy branch" in res.json()["error"]["message"]


def test_hall_must_be_in_the_class_branch(campus):
    cls = new_class(campus, hall_id=None)
    res = campus.owner.patch(f"/classes/{cls['id']}", {"hall_id": campus.kandy_hall["id"]})
    assert res.status_code == 422
    res = campus.owner.post(
        f"/classes/{cls['id']}/schedules",
        slot(SATURDAY, "08:00", "10:00", hall_id=campus.kandy_hall["id"]),
    )
    assert res.status_code == 422


def test_schedule_uses_the_class_hall_by_default(campus):
    cls = new_class(campus)
    res = campus.owner.post(f"/classes/{cls['id']}/schedules", slot(SATURDAY, "08:00", "10:00"))
    assert res.status_code == 201, res.text
    assert res.json()["hall"]["name"] == "Hall A"
    assert res.json()["start_time"] == "08:00:00"

    res = campus.owner.post(f"/classes/{cls['id']}/schedules", slot(SATURDAY, "10:00", "09:00"))
    assert res.status_code == 422


def test_hall_clash(campus):
    first = new_class(campus)
    campus.owner.post(f"/classes/{first['id']}/schedules", slot(SATURDAY, "08:00", "10:00"))
    other = new_class(campus, teacher_id=campus.amara["id"], level="grade_9")

    res = campus.owner.post(f"/classes/{other['id']}/schedules", slot(SATURDAY, "09:00", "11:00"))
    assert res.status_code == 409
    assert error_code(res) == "hall_clash"
    assert res.json()["error"]["message"] == (
        "Hall A is taken by Grade 10 Mathematics – Class 1 on Saturday 08:00–10:00"
    )

    # Back to back is fine, and so is another hall or another day.
    path = f"/classes/{other['id']}/schedules"
    assert campus.owner.post(path, slot(SATURDAY, "10:00", "12:00")).status_code == 201
    hall_b = slot(SATURDAY, "08:00", "10:00", hall_id=campus.hall_b["id"])
    assert campus.owner.post(path, hall_b).status_code == 201
    assert campus.owner.post(path, slot(7, "08:00", "10:00")).status_code == 201


def test_teacher_clash_across_branches(campus):
    galle = new_class(campus)
    campus.owner.post(f"/classes/{galle['id']}/schedules", slot(SATURDAY, "08:00", "10:00"))
    kandy = new_class(campus, branch_id=campus.kdy["id"], hall_id=campus.kandy_hall["id"])

    res = campus.owner.post(f"/classes/{kandy['id']}/schedules", slot(SATURDAY, "09:30", "11:00"))
    assert res.status_code == 409
    assert error_code(res) == "teacher_clash"
    assert res.json()["error"]["message"].startswith("Sunil already teaches")


def test_inactive_classes_free_their_slots(campus):
    first = new_class(campus)
    campus.owner.post(f"/classes/{first['id']}/schedules", slot(SATURDAY, "08:00", "10:00"))
    campus.owner.patch(f"/classes/{first['id']}", {"is_active": False})

    other = new_class(campus, teacher_id=campus.amara["id"])
    res = campus.owner.post(f"/classes/{other['id']}/schedules", slot(SATURDAY, "08:00", "10:00"))
    assert res.status_code == 201

    # Now the first class can't come back into the same slot.
    res = campus.owner.patch(f"/classes/{first['id']}", {"is_active": True})
    assert res.status_code == 409
    assert error_code(res) == "hall_clash"


def test_changing_the_teacher_checks_their_timetable(campus):
    amaras = new_class(campus, teacher_id=campus.amara["id"])
    campus.owner.post(f"/classes/{amaras['id']}/schedules", slot(SATURDAY, "08:00", "10:00"))
    sunils = new_class(campus, hall_id=campus.hall_b["id"])
    campus.owner.post(f"/classes/{sunils['id']}/schedules", slot(SATURDAY, "08:00", "10:00"))

    res = campus.owner.patch(f"/classes/{sunils['id']}", {"teacher_id": campus.amara["id"]})
    assert res.status_code == 409
    assert error_code(res) == "teacher_clash"
    assert campus.owner.get(f"/classes/{sunils['id']}").json()["teacher"]["name"] == "Sunil"


def test_edit_and_delete_schedules(campus):
    cls = new_class(campus)
    schedule = campus.owner.post(
        f"/classes/{cls['id']}/schedules", slot(SATURDAY, "08:00", "10:00")
    ).json()

    res = campus.owner.patch(f"/schedules/{schedule['id']}", {"end_time": "11:00"})
    assert res.status_code == 200
    assert res.json()["end_time"] == "11:00:00"
    # Moving a slot doesn't clash with itself.
    assert campus.owner.patch(f"/schedules/{schedule['id']}", {"start_time": "08:30"}).is_success
    assert (
        campus.owner.patch(f"/schedules/{schedule['id']}", {"end_time": "08:00"}).status_code == 422
    )

    res = campus.owner.patch(f"/schedules/{schedule['id']}", {"hall_id": campus.hall_b["id"]})
    assert res.json()["hall"]["name"] == "Hall B"

    assert campus.owner.delete(f"/schedules/{schedule['id']}").status_code == 204
    assert campus.owner.get(f"/classes/{cls['id']}").json()["schedules"] == []


def test_timetable(db, campus):
    maths = new_class(campus)
    campus.owner.post(f"/classes/{maths['id']}/schedules", slot(SATURDAY, "10:00", "12:00"))
    campus.owner.post(f"/classes/{maths['id']}/schedules", slot(2, "15:00", "17:00"))
    kandy = new_class(campus, branch_id=campus.kdy["id"], hall_id=campus.kandy_hall["id"])
    campus.owner.post(f"/classes/{kandy['id']}/schedules", slot(SATURDAY, "14:00", "16:00"))

    entries = campus.owner.get("/timetable").json()
    assert [(e["weekday"], e["start_time"]) for e in entries] == [
        (2, "15:00:00"),
        (6, "10:00:00"),
        (6, "14:00:00"),
    ]
    assert entries[0]["tuition_class"]["title"] == "Grade 10 Mathematics – Class 1"

    galle = campus.owner.get("/timetable", params={"branch_id": campus.gal["id"]}).json()
    assert len(galle) == 2
    by_hall = campus.owner.get("/timetable", params={"hall_id": campus.kandy_hall["id"]}).json()
    assert len(by_hall) == 1

    staff = add_member(db, campus.owner, "staff@chain.lk", "staff", branch_ids=[campus.gal["id"]])
    assert len(staff.get("/timetable").json()) == 2


def test_list_and_filter_classes(db, campus):
    new_class(campus)
    new_class(campus, subject_id=campus.physics["id"], level="al", exam_year=2027)
    new_class(campus, branch_id=campus.kdy["id"], hall_id=None, level="grade_9")

    page = campus.owner.get("/classes").json()
    assert page["total"] == 3
    assert campus.owner.get("/classes", params={"q": "phys"}).json()["total"] == 1
    assert campus.owner.get("/classes", params={"level": "grade_9"}).json()["total"] == 1
    assert campus.owner.get("/classes", params={"exam_year": 2027}).json()["total"] == 1
    galle = campus.owner.get("/classes", params={"branch_id": campus.gal["id"]}).json()
    assert galle["total"] == 2


def test_branch_access_and_permissions(db, campus):
    kandy = new_class(campus, branch_id=campus.kdy["id"], hall_id=None)
    staff = add_member(db, campus.owner, "staff@chain.lk", "staff", branch_ids=[campus.gal["id"]])

    assert staff.get("/classes").json()["total"] == 0
    assert staff.get(f"/classes/{kandy['id']}").status_code == 404
    # Staff can see classes but not create them.
    res = staff.post(
        "/classes",
        {
            "branch_id": campus.gal["id"],
            "subject_id": campus.maths["id"],
            "teacher_id": campus.sunil["id"],
            "level": "grade_10",
            "monthly_fee": "2000",
        },
    )
    assert res.status_code == 403
