"""Class days from the timetable, holidays, cancelling, extra days, door scans and marking."""

from datetime import date, datetime, timedelta

import pytest

from tests.helpers import add_member, enroll, error_code, future_month, new_class, new_student, slot


@pytest.fixture
def day10():
    """The 10th of a month two months from now (within the warning days)."""
    m = future_month(2)
    return date(m.year, m.month, 10)


@pytest.fixture
def setup(campus, freeze, day10):
    """Grade 10 maths in Galle meets on day10's weekday, 08:00–10:00 in Hall A.
    Kasun joined on the 1st of that month and hasn't paid. The clock is on day10 at 07:45."""
    freeze(datetime.combine(day10, datetime.min.time()).replace(hour=7, minute=45))
    cls = new_class(campus)
    schedule = campus.owner.post(
        f"/classes/{cls['id']}/schedules", slot(day10.isoweekday(), "08:00", "10:00")
    ).json()
    kasun = new_student(campus.owner, campus.gal["id"])
    enrollment = enroll(campus.owner, kasun, cls, joined_on=str(day10.replace(day=1))).json()
    return cls, schedule, kasun, enrollment


def days(api, start, end, **params):
    res = api.get("/sessions", params={"date_from": str(start), "date_to": str(end), **params})
    assert res.status_code == 200, res.text
    return res.json()


def scan(api, branch, student, **fields):
    body = {"branch_id": branch["id"], "qr_token": student["qr_token"], **fields}
    res = api.post("/attendance/scan", body)
    assert res.status_code == 200, res.text
    return res.json()


def pay_month(api, student, enrollment, day):
    item = {"kind": "monthly", "enrollment_id": enrollment["id"], "month": day.strftime("%Y-%m")}
    res = api.post(
        "/payments",
        {
            "student_id": student["id"],
            "branch_id": enrollment["tuition_class"]["branch_id"],
            "items": [item],
        },
    )
    assert res.status_code == 201, res.text


# Class days


def test_class_days_come_from_the_timetable(campus, setup, day10):
    week_later = day10 + timedelta(days=7)
    found = days(campus.owner, day10, day10 + timedelta(days=13))
    assert [(s["date"], s["start_time"], s["kind"]) for s in found] == [
        (str(day10), "08:00:00", "regular"),
        (str(week_later), "08:00:00", "regular"),
    ]
    # Looking again doesn't make duplicates.
    assert len(days(campus.owner, day10, day10 + timedelta(days=13))) == 2


def test_ranges_are_limited(campus, setup, day10):
    res = campus.owner.get(
        "/sessions", params={"date_from": str(day10), "date_to": str(day10 + timedelta(days=90))}
    )
    assert res.status_code == 422


def test_holidays_have_no_classes(campus, setup, day10):
    week_later = day10 + timedelta(days=7)
    days(campus.owner, day10, week_later)  # make the days first
    campus.owner.post(
        "/holidays", {"date": str(week_later), "name": "Poya", "branch_id": campus.gal["id"]}
    )
    campus.owner.post(
        "/holidays", {"date": str(day10), "name": "Kandy only", "branch_id": campus.kdy["id"]}
    )
    assert [s["date"] for s in days(campus.owner, day10, week_later)] == [str(day10)]


def test_cancel_and_restore_a_day(campus, setup, day10):
    session = days(campus.owner, day10, day10)[0]
    assert campus.owner.get(f"/sessions/{session['id']}").json()["date"] == str(day10)
    res = campus.owner.patch(f"/sessions/{session['id']}", {"status": "cancelled"})
    assert res.json()["status"] == "cancelled"
    # It stays cancelled; it isn't made again.
    assert days(campus.owner, day10, day10)[0]["status"] == "cancelled"
    res = campus.owner.patch(f"/sessions/{session['id']}", {"status": "scheduled"})
    assert res.json()["status"] == "scheduled"


def test_changing_the_weekly_time_redoes_future_days(campus, setup, day10):
    _, schedule, kasun, _ = setup
    week_later = day10 + timedelta(days=7)
    days(campus.owner, day10, week_later)
    scan(campus.owner, campus.gal, kasun)  # attendance on day10 keeps that day as it was

    campus.owner.patch(f"/schedules/{schedule['id']}", {"start_time": "09:00", "end_time": "11:00"})
    assert [(s["date"], s["start_time"]) for s in days(campus.owner, day10, week_later)] == [
        (str(day10), "08:00:00"),
        (str(week_later), "09:00:00"),
    ]


def test_extra_days_and_their_clashes(campus, setup, day10):
    cls, _, _, _ = setup
    extra_day = day10 + timedelta(days=2)
    res = campus.owner.post(
        f"/classes/{cls['id']}/sessions",
        {"date": str(extra_day), "start_time": "13:00", "end_time": "15:00", "note": "Revision"},
    )
    assert res.status_code == 201, res.text
    assert res.json()["kind"] == "extra"
    assert res.json()["hall"]["name"] == "Hall A"

    other = new_class(campus, teacher_id=campus.amara["id"], level="grade_9")
    res = campus.owner.post(
        f"/classes/{other['id']}/sessions",
        {"date": str(extra_day), "start_time": "14:00", "end_time": "16:00"},
    )
    assert res.status_code == 422
    assert error_code(res) == "hall_clash"
    # Sunil is busy with the regular class on day10.
    res = campus.owner.post(
        f"/classes/{cls['id']}/sessions",
        {
            "date": str(day10),
            "start_time": "09:00",
            "end_time": "11:00",
            "hall_id": campus.hall_b["id"],
        },
    )
    assert error_code(res) == "teacher_clash"


def test_closing_a_class_drops_its_future_days(campus, setup, day10):
    cls, _, _, _ = setup
    days(campus.owner, day10, day10 + timedelta(days=7))
    campus.owner.patch(f"/classes/{cls['id']}", {"is_active": False})
    assert days(campus.owner, day10, day10 + timedelta(days=7)) == []


# Door scan


def test_scan_unpaid_in_the_warning_days(campus, setup, day10):
    _, _, kasun, _ = setup
    result = scan(campus.owner, campus.gal, kasun)
    assert result["outcome"] == "in"
    assert result["fee_status"] == "warning"
    assert result["attendance_status"] == "present"
    assert result["amount_due"] == "2000.00"
    assert result["message"].endswith("fee not paid. Please pay by the 14th.")
    assert result["session"]["tuition_class"]["title"] == "Grade 10 Mathematics – Class 1"

    again = scan(campus.owner, campus.gal, kasun)
    assert again["outcome"] == "already"
    assert again["message"] == "Kasun Perera was marked at 07:45"


def test_scan_unpaid_after_the_warning_days_is_blocked(campus, setup, freeze, day10):
    _, _, kasun, enrollment = setup
    day17 = day10 + timedelta(days=7)
    freeze(datetime.combine(day17, datetime.min.time()).replace(hour=8, minute=20))

    result = scan(campus.owner, campus.gal, kasun)
    assert result["outcome"] == "blocked"
    assert result["fee_status"] == "blocked"
    assert result["attendance_status"] is None
    session = result["session"]
    roster = campus.owner.get(f"/sessions/{session['id']}/attendance").json()
    assert roster[0]["attendance"] is None  # nothing was marked

    # Paid: welcome, and 08:20 is more than 15 minutes late.
    pay_month(campus.owner, kasun, enrollment, day17)
    result = scan(campus.owner, campus.gal, kasun)
    assert result["outcome"] == "in"
    assert result["fee_status"] == "paid"
    assert result["attendance_status"] == "late"
    assert result["message"] == "Welcome, Kasun Perera"


def test_free_cards_count_as_paid(campus, setup, freeze, day10):
    _, _, kasun, enrollment = setup
    campus.owner.patch(f"/enrollments/{enrollment['id']}", {"card_type": "free"})
    freeze(datetime.combine(day10 + timedelta(days=7), datetime.min.time()).replace(hour=8))
    assert scan(campus.owner, campus.gal, kasun)["fee_status"] == "paid"


def test_scan_finds_no_class(campus, setup, freeze, day10):
    _, _, kasun, _ = setup
    freeze(datetime.combine(day10, datetime.min.time()).replace(hour=10, minute=30))
    assert scan(campus.owner, campus.gal, kasun)["outcome"] == "no_class"
    freeze(datetime.combine(day10, datetime.min.time()).replace(hour=7, minute=45))
    # Not at this branch.
    assert scan(campus.owner, campus.kdy, kasun)["outcome"] == "no_class"


def test_scan_by_code_and_bad_cards(campus, setup, day10):
    _, _, kasun, _ = setup
    body = {"branch_id": campus.gal["id"], "student_code": kasun["code"].lower()}
    assert campus.owner.post("/attendance/scan", body).json()["outcome"] == "in"

    res = campus.owner.post("/attendance/scan", {"branch_id": campus.gal["id"], "qr_token": "nope"})
    assert res.status_code == 404
    old_token = kasun["qr_token"]
    campus.owner.post(f"/students/{kasun['id']}/new-card")
    res = campus.owner.post(
        "/attendance/scan", {"branch_id": campus.gal["id"], "qr_token": old_token}
    )
    assert res.status_code == 404
    assert campus.owner.post("/attendance/scan", {"branch_id": campus.gal["id"]}).status_code == 422


# Marking by hand


def test_mark_attendance_by_hand(db, campus, setup, freeze, day10):
    _, _, kasun, _ = setup
    dilini = new_student(campus.owner, campus.gal["id"], name="Dilini")
    cls = setup[0]
    enroll(campus.owner, dilini, cls, joined_on=str(day10.replace(day=1)), card_type="free")
    day17 = day10 + timedelta(days=7)
    freeze(datetime.combine(day17, datetime.min.time()).replace(hour=9))
    session = days(campus.owner, day17, day17)[0]
    url = f"/sessions/{session['id']}/attendance"

    roster = campus.owner.get(url).json()
    assert [(r["student"]["name"], r["fee_status"]) for r in roster] == [
        ("Dilini", "paid"),
        ("Kasun Perera", "blocked"),
    ]

    # No override: unpaid Kasun can't be marked in after the 14th.
    marks = [{"student_id": kasun["id"], "status": "present"}]
    res = campus.owner.put(url, {"marks": marks})
    assert res.status_code == 422
    assert error_code(res) == "fee_blocked"

    staff = add_member(db, campus.owner, "staff@chain.lk", "staff", branch_ids=[campus.gal["id"]])
    res = staff.put(
        url,
        {
            "marks": [
                {"student_id": dilini["id"], "status": "present"},
                {"student_id": kasun["id"], "status": "absent"},
            ]
        },
    )
    assert res.status_code == 200, res.text
    assert [r["attendance"]["status"] for r in res.json()] == ["present", "absent"]
    assert days(campus.owner, day17, day17)[0]["counts"] == {"present": 1, "late": 0, "absent": 1}

    history = campus.owner.get(
        "/attendance",
        params={"student_id": dilini["id"], "date_from": str(day10), "date_to": str(day17)},
    ).json()
    assert [(h["session"]["date"], h["status"], h["method"]) for h in history] == [
        (str(day17), "present", "manual")
    ]


def test_no_marking_ahead_or_on_cancelled_days(campus, setup, day10):
    _, _, kasun, _ = setup
    week_later = day10 + timedelta(days=7)
    future, today = (
        days(campus.owner, week_later, week_later)[0],
        days(campus.owner, day10, day10)[0],
    )
    marks = {"marks": [{"student_id": kasun["id"], "status": "present"}]}
    assert campus.owner.put(f"/sessions/{future['id']}/attendance", marks).status_code == 422

    campus.owner.patch(f"/sessions/{today['id']}", {"status": "cancelled"})
    assert campus.owner.put(f"/sessions/{today['id']}/attendance", marks).status_code == 422
    assert scan(campus.owner, campus.gal, kasun)["outcome"] == "no_class"


def test_marked_days_cant_be_cancelled(campus, setup, day10):
    _, _, kasun, _ = setup
    session = scan(campus.owner, campus.gal, kasun)["session"]
    res = campus.owner.patch(f"/sessions/{session['id']}", {"status": "cancelled"})
    assert res.status_code == 422
