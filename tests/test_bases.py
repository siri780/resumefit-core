import pytest

from app.ats import load_skills
from app.bases import BASES, guess_base, load_base, pick_base
from app.latex_io import get_bullets


@pytest.mark.parametrize("name", list(BASES))
def test_base_has_placeholders_and_bullets(name):
    tex = load_base(name)
    assert "{{PHONE}}" in tex and "{{EMAIL}}" in tex
    assert "361-1543" not in tex
    assert len(get_bullets(tex)) >= 10


@pytest.mark.parametrize("title, expected", [
    ("Senior Data Scientist, Ads", "Data Scientist"),
    ("Machine Learning Engineer", "ML Engineer"),
    ("Software Engineer, Machine Learning", "ML Engineer"),
    ("Backend Software Engineer", "Software Engineer"),
    ("Product Analyst", "Data Scientist"),
    ("Data Engineer", "Software Engineer"),
    ("AI Engineer, LLM Platform", "ML Engineer"),
    ("Member of Technical Staff", None),
])
def test_guess_base(title, expected):
    assert guess_base(title) == expected


def test_clear_title_uses_only_that_base():
    jd = "Java, REST APIs, CI/CD, unit testing, OOP and Agile."
    name, _, how = pick_base("Data Scientist", jd, load_skills())
    assert (name, how) == ("Data Scientist", "title")


def test_unclear_title_falls_back_to_best_match():
    jd = "Java, REST APIs, CI/CD, unit testing, OOP and Agile."
    name, result, how = pick_base("Member of Technical Staff", jd, load_skills())
    assert how == "match"
    # every resume now lists these engineering basics, so any of them can tie at 100%
    assert name in ("Data Scientist", "ML Engineer", "Software Engineer")
    assert result["percent"] == 100
