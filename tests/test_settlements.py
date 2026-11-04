"""Teacher settlements: collections, the institute's share, payouts and balances."""

from datetime import datetime

import pytest

from app.common.schemas import add_months
from tests.helpers import add_member, enroll, future_month, new_class, new_student, ym


@pytest.fixture
def setup(campus, freeze):
    """In month m: Sunil (institute takes 20%) has Kasun and Dilini at Rs. 2000; Amara (0%)
    has Nimal at Rs. 1500. Everyone paid, plus Rs. 1000 admission each. Clock: m, the 10th."""
    m = future_month(2)
    freeze(datetime(m.year, m.month, 10, 9, 0))
    owner = campus.owner
    owner.patch("/settings", {"admission_fee": "1000", "tute_institute_share_percent": 10})
    owner.patch(f"/teachers/{campus.sunil['id']}", {"institute_share_percent": 20})
    sunils = new_class(campus)
    amaras = new_class(
        campus, teacher_id=campus.amara["id"], monthly_fee="1500", hall_id=campus.hall_b["id"]
    )
    people = {}
    for name, cls in [("Kasun", sunils), ("Dilini", sunils), ("Nimal", amaras)]:
        student = new_student(owner, campus.gal["id"], name=name)
        e = enroll(owner, student, cls, joined_on=f"{ym(m)}-01").json()
        res = owner.post(
            "/payments",
            {
                "student_id": student["id"],
                "branch_id": campus.gal["id"],
                "items": [
                    {"kind": "admission"},
                    {"kind": "monthly", "enrollment_id": e["id"], "month": ym(m)},
                ],
            },
        )
        assert res.status_code == 201, res.text
        people[name] = (student, e, res.json())
    return m, sunils, people


def rows(api, m):
    res = api.get("/settlements", params={"month": ym(m)})
    assert res.status_code == 200, res.text
    body = res.json()
    return body, {r["teacher"]["name"]: r for r in body["rows"]}


def test_month_settlement(campus, setup):
    m, _, _ = setup
    body, by_name = rows(campus.owner, m)
    sunil, amara = by_name["Sunil"], by_name["Amara"]
    assert (sunil["collected"], sunil["institute_share"], sunil["teacher_share"]) == (
        "4000.00",
        "800.00",
        "3200.00",
    )
    assert (amara["collected"], amara["institute_share"], amara["teacher_share"]) == (
        "1500.00",
        "0.00",
        "1500.00",
    )
    assert sunil["balance"] == "3200.00"
    # Admission fees are the institute's and aren't in anyone's settlement.
    assert body["collected"] == "5500.00"


def test_paid_tutes_use_the_tute_share(campus, setup):
    m, sunils, people = setup
    tute = campus.owner.post(
        "/tutes",
        {
            "title": "Paper",
            "month": ym(m),
            "class_ids": [sunils["id"]],
            "access_type": "paid",
            "price": "300",
        },
    ).json()
    kasun = people["Kasun"][0]
    campus.owner.post(
        "/payments",
        {
            "student_id": kasun["id"],
            "branch_id": campus.gal["id"],
            "items": [{"kind": "tute", "tute_id": tute["id"]}],
        },
    )
    _, by_name = rows(campus.owner, m)
    sunil = by_name["Sunil"]
    assert (sunil["class_fees"], sunil["tutes"]) == ("4000.00", "300.00")
    assert sunil["institute_share"] == "830.00"  # 20% of 4000 + 10% of 300


def test_a_new_share_doesnt_change_past_receipts(campus, setup):
    m, _, _ = setup
    campus.owner.patch(f"/teachers/{campus.sunil['id']}", {"institute_share_percent": 50})
    _, by_name = rows(campus.owner, m)
    assert by_name["Sunil"]["institute_share"] == "800.00"
    assert by_name["Sunil"]["share_percent"] == "50.00"  # shown as it is now


def test_voided_receipts_drop_out(campus, setup):
    m, _, people = setup
    receipt = people["Kasun"][2]
    campus.owner.post(f"/payments/{receipt['id']}/void", {"reason": "Mistake"})
    _, by_name = rows(campus.owner, m)
    assert by_name["Sunil"]["collected"] == "2000.00"


def test_payouts_and_balances(campus, setup, freeze):
    m, _, _ = setup
    sunil_id = campus.sunil["id"]
    res = campus.owner.post(
        "/payouts", {"teacher_id": sunil_id, "month": ym(m), "amount": "2000", "note": "Part"}
    )
    assert res.status_code == 201, res.text
    payout = res.json()
    assert payout["paid_by"]["name"] == "Owner chain"
    _, by_name = rows(campus.owner, m)
    assert (by_name["Sunil"]["paid"], by_name["Sunil"]["balance"]) == ("2000.00", "1200.00")

    # Paying more than the share leaves a negative balance (paid ahead).
    campus.owner.post("/payouts", {"teacher_id": sunil_id, "month": ym(m), "amount": "1500"})
    _, by_name = rows(campus.owner, m)
    assert by_name["Sunil"]["balance"] == "-300.00"

    # A mistake is voided, not deleted.
    void = campus.owner.post(f"/payouts/{payout['id']}/void", {"reason": "Wrong teacher"})
    assert void.json()["status"] == "void"
    assert (
        campus.owner.post(f"/payouts/{payout['id']}/void", {"reason": "Again"}).status_code == 422
    )
    _, by_name = rows(campus.owner, m)
    assert by_name["Sunil"]["paid"] == "1500.00"

    too_far = {"teacher_id": sunil_id, "month": ym(add_months(m, 3)), "amount": "10"}
    assert campus.owner.post("/payouts", too_far).status_code == 422
    assert (
        campus.owner.post("/payouts", {**too_far, "month": ym(m), "amount": "0"}).status_code == 422
    )


def test_teacher_history(campus, setup, freeze):
    m, sunils, people = setup
    # Next month: Kasun pays again.
    nxt = add_months(m, 1)
    freeze(datetime(nxt.year, nxt.month, 5, 9, 0))
    kasun, e, _ = people["Kasun"]
    campus.owner.post(
        "/payments",
        {
            "student_id": kasun["id"],
            "branch_id": campus.gal["id"],
            "items": [{"kind": "monthly", "enrollment_id": e["id"], "month": ym(nxt)}],
        },
    )
    campus.owner.post(
        "/payouts", {"teacher_id": campus.sunil["id"], "month": ym(m), "amount": "3200"}
    )
    history = campus.owner.get(f"/settlements/teachers/{campus.sunil['id']}").json()
    assert [(r["month"], r["teacher_share"], r["paid"]) for r in history["months"]] == [
        (ym(nxt), "1600.00", "0.00"),
        (ym(m), "3200.00", "3200.00"),
    ]
    assert history["owed"] == "1600.00"
    assert [p["amount"] for p in history["payouts"]] == ["3200.00"]


def test_who_can_see_settlements(db, campus, setup):
    m, _, _ = setup
    params = {"month": ym(m)}
    manager = add_member(db, campus.owner, "bm@chain.lk", "branch_manager", all_branches=True)
    assert manager.get("/settlements", params=params).status_code == 403  # not given by default

    limited = add_member(
        db,
        campus.owner,
        "acc@chain.lk",
        "staff",
        branch_ids=[campus.gal["id"]],
        permission_codes=["settlements.view"],
    )
    res = limited.get("/settlements", params=params)
    assert res.status_code == 403  # settlements cover every branch
