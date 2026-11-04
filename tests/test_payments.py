"""Dues, receipts and their numbers, discounts, voiding and cash handover."""

from datetime import datetime

import pytest

from app.common.schemas import add_months
from tests.helpers import add_member, enroll, error_code, future_month, new_class, new_student, ym


@pytest.fixture
def m1():
    return future_month(2)


@pytest.fixture
def setup(campus, freeze, m1):
    """Kasun joined Grade 10 maths (Rs. 2000) in Galle on the 20th of m1. Admission is 1000.
    The clock is on the 10th of the month after."""
    freeze(datetime(add_months(m1, 1).year, add_months(m1, 1).month, 10, 9, 0))
    campus.owner.patch("/settings", {"admission_fee": "1000"})
    cls = new_class(campus)
    kasun = new_student(campus.owner, campus.gal["id"])
    enrollment = enroll(campus.owner, kasun, cls, joined_on=f"{ym(m1)}-20").json()
    return cls, kasun, enrollment


def pay(api, student, branch, *items, method="cash"):
    return api.post(
        "/payments",
        {"student_id": student["id"], "branch_id": branch["id"], "method": method, "items": items},
    )


def month(enrollment, m):
    return {"kind": "monthly", "enrollment_id": enrollment["id"], "month": ym(m)}


ADMISSION = {"kind": "admission"}


def test_dues_include_admission_and_the_late_join_discount(campus, setup, m1):
    _, kasun, _ = setup
    dues = campus.owner.get(f"/students/{kasun['id']}/dues").json()
    assert dues["admission_fee"] == "1000.00"
    assert [(d["month"], d["amount"], d["late_join"]) for d in dues["months"]] == [
        (ym(m1), "1000.00", True),  # joined on the 20th: 50% off the first month
        (ym(add_months(m1, 1)), "2000.00", False),
    ]
    assert dues["total"] == "4000.00"

    later = campus.owner.get(
        f"/students/{kasun['id']}/dues", params={"until": ym(add_months(m1, 3))}
    ).json()
    assert len(later["months"]) == 4


@pytest.mark.parametrize(
    ("card", "stacking", "first_month"),
    [
        ("half", "both", "500.00"),  # half of half
        ("half", "best_only", "1000.00"),  # only the bigger discount
        ("free", "both", None),  # nothing to pay at all
    ],
)
def test_cards_and_discount_stacking(campus, setup, m1, card, stacking, first_month):
    _, kasun, enrollment = setup
    campus.owner.patch("/settings", {"discount_stacking": stacking})
    campus.owner.patch(f"/enrollments/{enrollment['id']}", {"card_type": card})

    months = campus.owner.get(f"/students/{kasun['id']}/dues").json()["months"]
    if first_month is None:
        assert months == []
    else:
        assert months[0]["amount"] == first_month
        assert months[0]["card_type"] == card


def test_collect_a_payment(campus, setup, m1):
    _, kasun, enrollment = setup
    res = pay(campus.owner, kasun, campus.gal, ADMISSION, month(enrollment, m1))
    assert res.status_code == 201, res.text
    receipt = res.json()
    assert receipt["receipt_no"] == "GAL-000001"
    assert receipt["amount"] == "2000.00"
    assert receipt["status"] == "valid"
    assert receipt["collected_by"]["name"] == "Owner chain"
    lines = {i["kind"]: i for i in receipt["items"]}
    assert lines["admission"]["amount"] == "1000.00"
    assert lines["monthly"]["full_amount"] == "2000.00"
    assert lines["monthly"]["amount"] == "1000.00"
    assert lines["monthly"]["late_join"] is True
    assert lines["monthly"]["tuition_class"]["title"] == "Grade 10 Mathematics – Class 1"

    dues = campus.owner.get(f"/students/{kasun['id']}/dues").json()
    assert dues["admission_fee"] is None
    assert [d["month"] for d in dues["months"]] == [ym(add_months(m1, 1))]

    again = pay(campus.owner, kasun, campus.gal, month(enrollment, m1))
    assert again.status_code == 409
    assert "already paid" in again.json()["error"]["message"]
    assert pay(campus.owner, kasun, campus.gal, ADMISSION).status_code == 409

    # Paying ahead is fine, and receipts keep counting per branch.
    next_one = pay(campus.owner, kasun, campus.gal, month(enrollment, add_months(m1, 2)))
    assert next_one.json()["receipt_no"] == "GAL-000002"


def test_receipts_are_numbered_per_branch(campus, setup, m1):
    _, kasun, enrollment = setup
    kandy_class = new_class(campus, branch_id=campus.kdy["id"], hall_id=None)
    kandy = enroll(campus.owner, kasun, kandy_class, joined_on=f"{ym(m1)}-01").json()
    pay(campus.owner, kasun, campus.gal, month(enrollment, m1))
    res = pay(campus.owner, kasun, campus.kdy, month(kandy, m1))
    assert res.json()["receipt_no"] == "KDY-000001"

    # A Kandy class can't go on a Galle receipt.
    res = pay(campus.owner, kasun, campus.gal, month(kandy, add_months(m1, 1)))
    assert res.status_code == 422
    assert "paid at the Kandy branch" in res.json()["error"]["message"]


def test_what_cant_be_paid(campus, setup, m1):
    _, kasun, enrollment = setup
    before_joining = month(enrollment, add_months(m1, -1))
    assert pay(campus.owner, kasun, campus.gal, before_joining).status_code == 422
    too_far = month(enrollment, add_months(m1, 15))
    assert pay(campus.owner, kasun, campus.gal, too_far).status_code == 422
    twice = month(enrollment, m1)
    assert pay(campus.owner, kasun, campus.gal, twice, twice).status_code == 422

    dilini = new_student(campus.owner, campus.gal["id"], name="Dilini")
    assert pay(campus.owner, dilini, campus.gal, month(enrollment, m1)).status_code == 422

    campus.owner.patch(f"/enrollments/{enrollment['id']}", {"card_type": "free"})
    res = pay(campus.owner, kasun, campus.gal, month(enrollment, m1))
    assert res.status_code == 422
    assert "nothing to pay" in res.json()["error"]["message"]

    res = campus.owner.post(
        "/payments", {"student_id": kasun["id"], "branch_id": campus.gal["id"], "items": []}
    )
    assert res.status_code == 422


def test_leaving_limits_the_months(campus, setup, m1):
    _, kasun, enrollment = setup
    campus.owner.post(f"/enrollments/{enrollment['id']}/leave", {"end_month": ym(m1)})
    dues = campus.owner.get(
        f"/students/{kasun['id']}/dues", params={"until": ym(add_months(m1, 4))}
    ).json()
    assert [d["month"] for d in dues["months"]] == [ym(m1)]
    after = month(enrollment, add_months(m1, 1))
    assert pay(campus.owner, kasun, campus.gal, after).status_code == 422


def test_void_a_receipt(db, campus, setup, m1):
    _, kasun, enrollment = setup
    receipt = pay(campus.owner, kasun, campus.gal, month(enrollment, m1)).json()
    staff = add_member(db, campus.owner, "staff@chain.lk", "staff", branch_ids=[campus.gal["id"]])

    void = f"/payments/{receipt['id']}/void"
    assert staff.post(void, {"reason": "Wrong month"}).status_code == 403
    assert campus.owner.post(void, {"reason": ""}).status_code == 422
    res = campus.owner.post(void, {"reason": "Wrong month"})
    assert res.status_code == 200
    assert res.json()["status"] == "void"
    assert res.json()["voided_by"]["name"] == "Owner chain"
    assert campus.owner.post(void, {"reason": "Again"}).status_code == 422

    # The month is owed again and can be paid on a new receipt.
    dues = campus.owner.get(f"/students/{kasun['id']}/dues").json()
    assert ym(m1) in [d["month"] for d in dues["months"]]
    res = pay(campus.owner, kasun, campus.gal, month(enrollment, m1))
    assert res.status_code == 201
    assert res.json()["receipt_no"] == "GAL-000002"


def test_list_receipts(db, campus, setup, m1):
    _, kasun, enrollment = setup
    first = pay(campus.owner, kasun, campus.gal, month(enrollment, m1)).json()
    pay(campus.owner, kasun, campus.gal, month(enrollment, add_months(m1, 1)), method="card")
    campus.owner.post(f"/payments/{first['id']}/void", {"reason": "Mistake"})

    page = campus.owner.get("/payments").json()
    assert [p["receipt_no"] for p in page["items"]] == ["GAL-000002", "GAL-000001"]
    assert campus.owner.get("/payments", params={"status": "void"}).json()["total"] == 1
    assert campus.owner.get("/payments", params={"q": "000002"}).json()["total"] == 1
    mine = campus.owner.get("/payments", params={"student_id": kasun["id"]}).json()
    assert mine["total"] == 2

    kandy_staff = add_member(
        db, campus.owner, "kdy@chain.lk", "staff", branch_ids=[campus.kdy["id"]]
    )
    assert kandy_staff.get("/payments").json()["total"] == 0
    assert kandy_staff.get(f"/payments/{first['id']}").status_code == 404


def test_cash_handover(db, campus, setup, m1):
    _, kasun, enrollment = setup
    gal = [campus.gal["id"]]
    staff = add_member(db, campus.owner, "staff@chain.lk", "staff", branch_ids=gal)
    manager = add_member(db, campus.owner, "bm@chain.lk", "branch_manager", branch_ids=gal)

    pay(staff, kasun, campus.gal, ADMISSION)
    pay(staff, kasun, campus.gal, month(enrollment, m1))
    pay(staff, kasun, campus.gal, month(enrollment, add_months(m1, 1)), method="card")

    # Staff see only their own cash; the manager sees everyone's.
    mine = staff.get("/cash/in-hand").json()
    assert [(c["collected_by"]["name"], c["amount"], c["receipts"]) for c in mine] == [
        ("staff", "2000.00", 2)
    ]
    assert len(manager.get("/cash/in-hand").json()) == 1

    staff_user = mine[0]["collected_by"]["id"]
    body = {"collected_by_id": staff_user, "branch_id": campus.gal["id"]}
    assert staff.post("/cash/handovers", body).status_code == 403
    res = manager.post("/cash/handovers", {**body, "note": "Evening count"})
    assert res.status_code == 201, res.text
    handover = res.json()
    assert handover["amount"] == "2000.00"
    assert handover["received_by"]["name"] == "bm"

    assert manager.get("/cash/in-hand").json() == []
    assert manager.post("/cash/handovers", body).status_code == 422  # nothing left
    history = manager.get("/cash/handovers").json()
    assert [h["id"] for h in history["items"]] == [handover["id"]]
    receipts = manager.get("/payments").json()["items"]
    linked = sorted((r["method"], r["handover_id"]) for r in receipts)
    assert linked == [("card", None), ("cash", handover["id"]), ("cash", handover["id"])]


def test_nobody_receives_their_own_cash(db, campus, setup, m1):
    _, kasun, enrollment = setup
    pay(campus.owner, kasun, campus.gal, month(enrollment, m1))
    me = campus.owner.get("/cash/in-hand").json()[0]["collected_by"]["id"]
    res = campus.owner.post(
        "/cash/handovers", {"collected_by_id": me, "branch_id": campus.gal["id"]}
    )
    assert res.status_code == 422
    assert error_code(res) == "rule_violation"
