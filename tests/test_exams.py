"""Exams with parts, marks entry, and ranks worked out from the marks."""

from datetime import date, timedelta

import pytest

from tests.helpers import enroll, new_class, new_student


@pytest.fixture
def setup(campus):
    """One exam for two classes. Class 1: Kasun, Dilini, Amal. Class 2: Nimal."""
    start = date.today().replace(day=1)
    class1 = new_class(campus)
    class2 = new_class(
        campus, teacher_id=campus.amara["id"], name="Class 2", hall_id=campus.hall_b["id"]
    )
    people = {}
    for name, cls in [("Kasun", class1), ("Dilini", class1), ("Amal", class1), ("Nimal", class2)]:
        people[name] = new_student(campus.owner, campus.gal["id"], name=name)
        enroll(campus.owner, people[name], cls, joined_on=str(start))
    res = campus.owner.post(
        "/exams",
        {
            "title": "Term test 1",
            "date": str(date.today() + timedelta(days=1)),
            "class_ids": [class1["id"], class2["id"]],
            "parts": [{"name": "MCQ", "max_marks": 40}, {"name": "Essay", "max_marks": "60"}],
        },
    )
    assert res.status_code == 201, res.text
    return res.json(), class1, class2, people


def marks(exam, student, mcq, essay, absent=False):
    mcq_part, essay_part = exam["parts"]
    return [
        {"student_id": student["id"], "part_id": mcq_part["id"], "marks": mcq, "is_absent": absent},
        {
            "student_id": student["id"],
            "part_id": essay_part["id"],
            "marks": essay,
            "is_absent": absent,
        },
    ]


def test_create_exam(campus, setup):
    exam, *_ = setup
    assert exam["subject"]["name"] == "Mathematics"  # from the first class
    assert exam["teacher"]["name"] == "Sunil"
    assert [(p["name"], p["max_marks"]) for p in exam["parts"]] == [
        ("MCQ", "40.00"),
        ("Essay", "60.00"),
    ]
    assert exam["max_total"] == "100.00"
    assert exam["published"] is False
    assert campus.owner.get("/exams").json()["total"] == 1


def test_marks_and_ranks(campus, setup):
    exam, class1, class2, p = setup
    sheet = campus.owner.get(f"/exams/{exam['id']}/marks").json()
    assert [r["student"]["name"] for r in sheet] == ["Amal", "Dilini", "Kasun", "Nimal"]

    lines = (
        marks(exam, p["Kasun"], 35, "50")
        + marks(exam, p["Dilini"], 40, 45)
        + marks(exam, p["Nimal"], 20, 30.5)
        + marks(exam, p["Amal"], None, None, absent=True)
    )
    res = campus.owner.put(f"/exams/{exam['id']}/marks", {"marks": lines})
    assert res.status_code == 200, res.text

    result = campus.owner.get(f"/exams/{exam['id']}/results").json()
    assert (result["sat"], result["absent"]) == (3, 1)
    assert result["highest"] == "85.00"
    assert result["average"] == "73.50"  # (85 + 85 + 50.5) / 3
    summary = [
        (r["student"]["name"], r["total"], r["percent"], r["rank"], r["class_rank"], r["absent"])
        for r in result["rows"]
    ]
    assert summary == [
        ("Dilini", "85.00", "85.00", 1, 1, False),  # equal totals share the rank
        ("Kasun", "85.00", "85.00", 1, 1, False),
        ("Nimal", "50.50", "50.50", 3, 1, False),  # top of class 2
        ("Amal", None, None, None, None, True),
    ]


def test_marks_are_checked(campus, setup):
    exam, _, _, p = setup
    url = f"/exams/{exam['id']}/marks"
    too_many = marks(exam, p["Kasun"], 41, 10)
    assert campus.owner.put(url, {"marks": too_many}).status_code == 422
    missing = [{"student_id": p["Kasun"]["id"], "part_id": exam["parts"][0]["id"]}]
    assert campus.owner.put(url, {"marks": missing}).status_code == 422
    outsider = new_student(campus.owner, campus.gal["id"], name="Outsider")
    assert campus.owner.put(url, {"marks": marks(exam, outsider, 1, 1)}).status_code == 404

    # Changing a mark updates it.
    campus.owner.put(url, {"marks": marks(exam, p["Kasun"], 10, 10)})
    campus.owner.put(url, {"marks": marks(exam, p["Kasun"], 20, 10)})
    rows = campus.owner.get(f"/exams/{exam['id']}/results").json()["rows"]
    assert rows[0]["total"] == "30.00"


def test_parts_with_marks_are_protected(campus, setup):
    exam, _, _, p = setup
    mcq, essay = exam["parts"]
    campus.owner.put(f"/exams/{exam['id']}/marks", {"marks": marks(exam, p["Kasun"], 35, 50)})
    url = f"/exams/{exam['id']}"

    keep_only_mcq = {"parts": [{"id": mcq["id"], "name": "MCQ", "max_marks": 40}]}
    assert campus.owner.patch(url, keep_only_mcq).status_code == 422
    lower = {
        "parts": [
            {"id": mcq["id"], "name": "MCQ", "max_marks": 30},
            {"id": essay["id"], "name": "Essay", "max_marks": 60},
        ]
    }
    assert campus.owner.patch(url, lower).status_code == 422

    more = {
        "parts": [
            {"id": mcq["id"], "name": "MCQ", "max_marks": 40},
            {"id": essay["id"], "name": "Essay", "max_marks": 60},
            {"name": "Structured", "max_marks": 20},
        ]
    }
    res = campus.owner.patch(url, more)
    assert res.status_code == 200, res.text
    assert res.json()["max_total"] == "120.00"
    assert campus.owner.patch(url, {"published": True}).json()["published"] is True
