"""Free and paid tutes: who may have them, hard-copy ticks, paying on a receipt, soft copies."""

from datetime import datetime

import pytest

from tests.helpers import add_member, enroll, error_code, future_month, new_class, new_student, ym

PDF = b"%PDF-1.4\n% a tiny test file\n"


@pytest.fixture
def setup(campus, freeze):
    """Grade 10 maths (Rs. 2000) in Galle. Kasun pays full fees, Dilini has a free card.
    Both joined on the 1st of month m; the clock is on the 10th."""
    m = future_month(2)
    freeze(datetime(m.year, m.month, 10, 9, 0))
    cls = new_class(campus)
    kasun = new_student(campus.owner, campus.gal["id"])
    dilini = new_student(campus.owner, campus.gal["id"], name="Dilini")
    e_kasun = enroll(campus.owner, kasun, cls, joined_on=f"{ym(m)}-01").json()
    enroll(campus.owner, dilini, cls, joined_on=f"{ym(m)}-01", card_type="free")
    return m, cls, kasun, dilini, e_kasun


def new_tute(api, cls, m, **fields):
    body = {"title": "Algebra 1", "number": 1, "month": ym(m), "class_ids": [cls["id"]], **fields}
    res = api.post("/tutes", body)
    assert res.status_code == 201, res.text
    return res.json()


def pay(api, student, branch, *items):
    res = api.post(
        "/payments", {"student_id": student["id"], "branch_id": branch["id"], "items": items}
    )
    return res


def month_fee(enrollment, m):
    return {"kind": "monthly", "enrollment_id": enrollment["id"], "month": ym(m)}


def access(api, tute):
    rows = api.get(f"/tutes/{tute['id']}/students").json()
    return {r["student"]["name"]: (r["allowed"], r["reason"]) for r in rows}


def test_create_tutes(campus, setup):
    m, cls, *_ = setup
    tute = new_tute(campus.owner, cls, m)
    assert tute["teacher"]["name"] == "Sunil"  # from the class
    assert tute["access_type"] == "free"
    assert tute["price"] is None
    assert tute["has_file"] is False

    res = campus.owner.post(
        "/tutes",
        {"title": "Paper", "month": ym(m), "class_ids": [cls["id"]], "access_type": "paid"},
    )
    assert res.status_code == 422  # a paid tute needs a price
    paid = new_tute(campus.owner, cls, m, access_type="paid", price="300")
    assert paid["price"] == "300.00"

    listing = campus.owner.get("/tutes", params={"month": ym(m)}).json()
    assert listing["total"] == 2


def test_free_tute_needs_the_class_fee(campus, setup):
    m, cls, kasun, dilini, e_kasun = setup
    tute = new_tute(campus.owner, cls, m)
    assert access(campus.owner, tute) == {
        "Dilini": (True, None),  # free card counts as paid
        "Kasun Perera": (False, "class_fee_unpaid"),
    }

    res = campus.owner.post(f"/tutes/{tute['id']}/issues", {"student_id": kasun["id"]})
    assert res.status_code == 422
    assert error_code(res) == "class_fee_unpaid"

    pay(campus.owner, kasun, campus.gal, month_fee(e_kasun, m))
    res = campus.owner.post(f"/tutes/{tute['id']}/issues", {"student_id": kasun["id"]})
    assert res.status_code == 200
    assert res.json()["issued_at"] is not None
    rows = campus.owner.get(f"/tutes/{tute['id']}/students").json()
    assert [r["issued_at"] is not None for r in rows] == [False, True]

    assert campus.owner.delete(f"/tutes/{tute['id']}/issues/{kasun['id']}").status_code == 204
    assert campus.owner.delete(f"/tutes/{tute['id']}/issues/{kasun['id']}").status_code == 404


def test_paid_tute_needs_both_payments(campus, setup):
    m, cls, kasun, _, e_kasun = setup
    tute = new_tute(campus.owner, cls, m, access_type="paid", price="300")
    pay(campus.owner, kasun, campus.gal, month_fee(e_kasun, m))
    assert access(campus.owner, tute)["Kasun Perera"] == (False, "tute_unpaid")

    # It shows as something to buy, outside the fees total.
    dues = campus.owner.get(f"/students/{kasun['id']}/dues").json()
    assert dues["tutes"] == [
        {"tute_id": tute["id"], "title": "Algebra 1", "month": ym(m), "price": "300.00"}
    ]
    assert dues["total"] == "0.00"

    item = {"kind": "tute", "tute_id": tute["id"]}
    res = pay(campus.owner, kasun, campus.gal, item)
    assert res.status_code == 201, res.text
    line = res.json()["items"][0]
    assert (line["kind"], line["amount"], line["tute"]["title"]) == ("tute", "300.00", "Algebra 1")
    assert access(campus.owner, tute)["Kasun Perera"] == (True, None)
    assert campus.owner.get(f"/students/{kasun['id']}/dues").json()["tutes"] == []
    assert pay(campus.owner, kasun, campus.gal, item).status_code == 409

    # Voiding the receipt takes access away again.
    campus.owner.post(f"/payments/{res.json()['id']}/void", {"reason": "Refunded"})
    assert access(campus.owner, tute)["Kasun Perera"] == (False, "tute_unpaid")


def test_what_tutes_cant_be_bought(campus, setup):
    m, cls, kasun, _, _ = setup
    free = new_tute(campus.owner, cls, m)
    assert (
        pay(campus.owner, kasun, campus.gal, {"kind": "tute", "tute_id": free["id"]}).status_code
        == 422
    )

    kandy = new_class(campus, branch_id=campus.kdy["id"], hall_id=None)
    kandy_tute = new_tute(campus.owner, kandy, m, access_type="paid", price="200")
    res = pay(campus.owner, kasun, campus.gal, {"kind": "tute", "tute_id": kandy_tute["id"]})
    assert res.status_code == 422  # Kasun isn't in that class


def test_hard_copy_only_when_the_tute_has_one(campus, setup):
    m, cls, _, dilini, _ = setup
    tute = new_tute(campus.owner, cls, m, has_hard_copy=False)
    res = campus.owner.post(f"/tutes/{tute['id']}/issues", {"student_id": dilini["id"]})
    assert res.status_code == 422


def test_soft_copy_upload_and_download(campus, setup):
    m, cls, *_ = setup
    tute = new_tute(campus.owner, cls, m)
    url = f"/tutes/{tute['id']}/file"

    res = campus.owner.put(url, files={"file": ("notes.txt", b"hello", "text/plain")})
    assert res.status_code == 422
    res = campus.owner.put(url, files={"file": ("Algebra 1.pdf", PDF, "application/pdf")})
    assert res.status_code == 200, res.text
    assert res.json()["has_file"] is True
    assert res.json()["file_name"] == "Algebra 1.pdf"
    assert res.json()["file_size"] == len(PDF)

    download = campus.owner.get(url)
    assert download.status_code == 200
    assert download.content == PDF
    assert download.headers["content-type"] == "application/pdf"

    assert campus.owner.delete(url).json()["has_file"] is False
    assert campus.owner.get(url).status_code == 404


def test_tutes_follow_branch_access(db, campus, setup):
    m, cls, *_ = setup
    tute = new_tute(campus.owner, cls, m)
    kandy_staff = add_member(db, campus.owner, "k@chain.lk", "staff", branch_ids=[campus.kdy["id"]])
    assert kandy_staff.get(f"/tutes/{tute['id']}").status_code == 404
    assert kandy_staff.get("/tutes").json()["total"] == 0
    galle_staff = add_member(db, campus.owner, "g@chain.lk", "staff", branch_ids=[campus.gal["id"]])
    assert galle_staff.get(f"/tutes/{tute['id']}").status_code == 200
    # Staff can tick hard copies but not add tutes.
    assert (
        galle_staff.post(
            "/tutes", {"title": "X", "month": ym(m), "class_ids": [cls["id"]]}
        ).status_code
        == 403
    )
