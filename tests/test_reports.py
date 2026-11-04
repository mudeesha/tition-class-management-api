"""The dashboard, reports, and platform usage."""

from datetime import date, datetime

import pytest

from tests.helpers import add_member, enroll, future_month, new_class, new_student, slot, ym


@pytest.fixture
def setup(campus, freeze):
    """Grade 10 maths (Rs. 2000) meets today (the 10th of month m) 08:00–10:00.
    Kasun has paid this month in cash, Dilini hasn't. The clock is 09:00."""
    m = future_month(2)
    today = date(m.year, m.month, 10)
    freeze(datetime(m.year, m.month, 10, 9, 0))
    cls = new_class(campus)
    campus.owner.post(f"/classes/{cls['id']}/schedules", slot(today.isoweekday(), "08:00", "10:00"))
    kasun = new_student(campus.owner, campus.gal["id"], phone="0711111111")
    dilini = new_student(campus.owner, campus.gal["id"], name="Dilini", guardian_phone="0722222222")
    e_kasun = enroll(campus.owner, kasun, cls, joined_on=f"{ym(m)}-01").json()
    enroll(campus.owner, dilini, cls, joined_on=f"{ym(m)}-01")
    campus.owner.post(
        "/payments",
        {
            "student_id": kasun["id"],
            "branch_id": campus.gal["id"],
            "items": [{"kind": "monthly", "enrollment_id": e_kasun["id"], "month": ym(m)}],
        },
    )
    return m, today, cls, kasun, dilini


def test_dashboard(campus, setup):
    m, today, cls, kasun, _ = setup
    campus.owner.post(
        "/attendance/scan", {"branch_id": campus.gal["id"], "qr_token": kasun["qr_token"]}
    )
    board = campus.owner.get("/dashboard").json()
    assert board["date"] == str(today)
    assert [c["tuition_class"]["id"] for c in board["classes_today"]] == [cls["id"]]
    assert board["attendance_today"] == {"came": 1, "absent": 0}
    assert (board["collected_today"], board["receipts_today"]) == ("2000.00", 1)
    assert board["collected_this_month"] == "2000.00"
    assert board["cash_not_handed_over"] == "2000.00"
    assert board["unpaid_this_month"] == {"students": 1, "amount": "2000.00"}  # Dilini
    assert board["active_students"] == 2


def test_dashboard_follows_permissions(db, campus, setup):
    teacher = add_member(db, campus.owner, "t@chain.lk", "teacher", branch_ids=[campus.gal["id"]])
    board = teacher.get("/dashboard").json()
    assert board["classes_today"] is not None  # teachers see attendance
    assert board["collected_today"] is None  # but not money
    assert board["unpaid_this_month"] is None


def test_dues_report(campus, setup):
    _, _, _, _, dilini = setup
    report = campus.owner.get("/reports/dues").json()
    assert [(r["student"]["name"], r["amount"]) for r in report["rows"]] == [("Dilini", "2000.00")]
    assert report["rows"][0]["student"]["guardian_phone"] == "0722222222"
    assert report["total"] == "2000.00"


def test_collections_report(campus, setup):
    m, today, *_ = setup
    report = campus.owner.get(
        "/reports/collections", params={"date_from": f"{ym(m)}-01", "date_to": str(today)}
    ).json()
    assert [(d["date"], d["receipts"], d["total"], d["cash"]) for d in report["days"]] == [
        (str(today), 1, "2000.00", "2000.00")
    ]
    assert (report["class_fees"], report["admission"], report["total"]) == (
        "2000.00",
        "0.00",
        "2000.00",
    )
    too_long = {"date_from": "2026-01-01", "date_to": "2026-12-31"}
    assert campus.owner.get("/reports/collections", params=too_long).status_code == 422


def test_attendance_report(campus, setup):
    m, _, cls, kasun, _ = setup
    campus.owner.post(
        "/attendance/scan", {"branch_id": campus.gal["id"], "qr_token": kasun["qr_token"]}
    )
    report = campus.owner.get("/reports/attendance", params={"month": ym(m)}).json()
    [row] = report["rows"]
    assert row["tuition_class"]["id"] == cls["id"]
    assert (row["days"], row["students"], row["came"]) == (2, 2, 1)  # the 3rd and the 10th
    assert row["rate"] == "25.0"


def test_reports_need_the_permission(db, campus, setup):
    staff = add_member(db, campus.owner, "s@chain.lk", "staff", branch_ids=[campus.gal["id"]])
    assert staff.get("/reports/dues").status_code == 403


def test_platform_usage_and_summary(admin, campus, setup):
    tenants = admin.get("/platform/tenants").json()["items"]
    chain = next(t for t in tenants if t["code"] == "chain")
    assert chain["usage"] == {"students": 2, "teachers": 2, "branches": 3, "users": 1}
    summary = admin.get("/platform/summary").json()
    assert summary["institutes"] >= 1
    assert summary["active"] >= 1
    assert summary["students"] >= 2
