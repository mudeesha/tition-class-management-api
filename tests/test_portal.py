"""The student portal: logins made by staff, and what a student can see about themselves."""

from datetime import date, datetime, timedelta

import pytest

from tests.helpers import (
    enroll,
    error_code,
    future_month,
    login,
    new_class,
    new_student,
    skip_password_change,
    ym,
)

PDF = b"%PDF-1.4\n% a tiny test file\n"


@pytest.fixture
def setup(campus, client, db, freeze):
    """Kasun is in Grade 10 maths from month m and has a portal login. Clock: m, the 10th."""
    m = future_month(2)
    freeze(datetime(m.year, m.month, 10, 9, 0))
    cls = new_class(campus)
    kasun = new_student(campus.owner, campus.gal["id"])
    enrollment = enroll(campus.owner, kasun, cls, joined_on=f"{ym(m)}-01").json()
    res = campus.owner.put(f"/students/{kasun['id']}/portal", {"password": "first-pass-1"})
    assert res.status_code == 200, res.text
    return m, cls, kasun, enrollment


def sign_in(client, db, campus, username, password="first-pass-1"):
    skip_password_change(db, username)
    return login(client, username, password, tenant_id=campus.tenant.id)


def test_staff_open_a_portal_login(client, db, campus, setup):
    _, _, kasun, _ = setup
    account = campus.owner.get(f"/students/{kasun['id']}/portal").json()
    assert account == {"username": "chain-00001", "active": True}

    res = client.post(
        "/api/v1/auth/login", json={"login": "CHAIN-00001", "password": "first-pass-1"}
    )
    assert res.status_code == 200
    assert res.json()["must_change_password"] is True

    # A student is not a staff account.
    staff = campus.owner.get("/members").json()["items"]
    assert "Kasun Perera" not in [m["user"]["name"] for m in staff]


def test_student_sees_only_their_portal(client, db, campus, setup):
    _, _, kasun, _ = setup
    student = sign_in(client, db, campus, "chain-00001")
    me = student.get("/portal/me").json()
    assert me["code"] == "CHAIN-00001"
    assert [e["tuition_class"]["title"] for e in me["enrollments"]] == [
        "Grade 10 Mathematics – Class 1"
    ]
    context = student.get("/auth/context").json()
    assert context["role"]["key"] == "student"
    assert set(context["permissions"]) == {
        "portal.payments",
        "portal.attendance",
        "portal.tutes",
        "portal.marks",
    }
    # No staff screens.
    assert student.get("/students").status_code == 403
    assert student.get("/payments").status_code == 403
    # And the owner isn't a student.
    assert campus.owner.get("/portal/me").status_code == 404


def test_fees_receipts_and_attendance(client, db, campus, setup):
    m, _, kasun, enrollment = setup
    student = sign_in(client, db, campus, "chain-00001")
    assert student.get("/portal/dues").json()["total"] == "2000.00"

    campus.owner.post(
        "/payments",
        {
            "student_id": kasun["id"],
            "branch_id": campus.gal["id"],
            "items": [{"kind": "monthly", "enrollment_id": enrollment["id"], "month": ym(m)}],
        },
    )
    assert student.get("/portal/dues").json()["total"] == "0.00"
    assert [r["receipt_no"] for r in student.get("/portal/receipts").json()] == ["GAL-000001"]

    marked = student.get(
        "/portal/attendance", params={"date_from": str(m), "date_to": str(m + timedelta(days=27))}
    )
    assert marked.status_code == 200
    assert marked.json() == []


def test_tutes_in_the_portal(client, db, campus, setup):
    m, cls, kasun, enrollment = setup
    tute = campus.owner.post(
        "/tutes", {"title": "Algebra 1", "month": ym(m), "class_ids": [cls["id"]]}
    ).json()
    campus.owner.put(f"/tutes/{tute['id']}/file", files={"file": ("a.pdf", PDF, "application/pdf")})
    student = sign_in(client, db, campus, "chain-00001")

    listed = student.get("/portal/tutes").json()
    assert [(t["title"], t["allowed"], t["reason"], t["has_file"]) for t in listed] == [
        ("Algebra 1", False, "class_fee_unpaid", True)
    ]
    res = student.get(f"/portal/tutes/{tute['id']}/file")
    assert res.status_code == 422
    assert error_code(res) == "class_fee_unpaid"

    campus.owner.post(
        "/payments",
        {
            "student_id": kasun["id"],
            "branch_id": campus.gal["id"],
            "items": [{"kind": "monthly", "enrollment_id": enrollment["id"], "month": ym(m)}],
        },
    )
    assert student.get("/portal/tutes").json()[0]["allowed"] is True
    download = student.get(f"/portal/tutes/{tute['id']}/file")
    assert download.status_code == 200
    assert download.content == PDF


def test_only_published_marks_show(client, db, campus, setup):
    _, cls, kasun, _ = setup
    exam = campus.owner.post(
        "/exams",
        {
            "title": "Term test",
            "date": str(date.today() + timedelta(days=70)),
            "class_ids": [cls["id"]],
            "parts": [{"name": "Paper", "max_marks": 50}],
        },
    ).json()
    campus.owner.put(
        f"/exams/{exam['id']}/marks",
        {"marks": [{"student_id": kasun["id"], "part_id": exam["parts"][0]["id"], "marks": 42}]},
    )
    student = sign_in(client, db, campus, "chain-00001")
    assert student.get("/portal/exams").json() == []

    campus.owner.patch(f"/exams/{exam['id']}", {"published": True})
    [result] = student.get("/portal/exams").json()
    assert (result["title"], result["total"], result["percent"], result["rank"]) == (
        "Term test",
        "42.00",
        "84.00",
        1,
    )
    assert result["parts"] == [
        {"name": "Paper", "max_marks": "50.00", "marks": "42.00", "is_absent": False}
    ]


def test_reset_and_close_the_login(client, db, campus, setup):
    _, _, kasun, _ = setup
    student = sign_in(client, db, campus, "chain-00001")
    assert student.get("/portal/me").status_code == 200

    # A new password signs them out of the old session.
    campus.owner.put(f"/students/{kasun['id']}/portal", {"password": "second-pass-2"})
    assert student.get("/portal/me").status_code == 401

    campus.owner.delete(f"/students/{kasun['id']}/portal")
    again = sign_in(client, db, campus, "chain-00001", "second-pass-2")
    assert again.get("/portal/me").status_code == 403

    # Making the student inactive also closes it; reactivating opens it again.
    campus.owner.put(f"/students/{kasun['id']}/portal", {"password": "third-pass-3"})
    campus.owner.patch(f"/students/{kasun['id']}", {"is_active": False})
    third = sign_in(client, db, campus, "chain-00001", "third-pass-3")
    assert third.get("/portal/me").status_code == 403
    campus.owner.patch(f"/students/{kasun['id']}", {"is_active": True})
    assert third.get("/portal/me").status_code == 200
