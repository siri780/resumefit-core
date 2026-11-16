from pathlib import Path

from app.one_page import SQUEEZE_STEPS, fit_one_page, squeeze

TEX = r"\section{X}\resumeItem{aa}\resumeItem{bb}\resumeItem{cc}"
REAL = (Path(__file__).resolve().parent.parent / "data" / "resume_ds.tex").read_text(encoding="utf-8")


def edits():
    return [{"id": 0, "original": "aa", "new": "a" * 10},
            {"id": 1, "original": "bb", "new": "b" * 50},
            {"id": 2, "original": "cc", "new": "c" * 5}]


def fake(limit):
    """A fake build: the 'PDF' is the tex, and it fits if short enough."""
    return (lambda name, tex: tex), (lambda tex: 1 if len(tex) <= limit else 2)


def test_keeps_all_edits_when_they_fit():
    build, count = fake(10_000)
    tex, pdf, kept, dropped = fit_one_page(TEX, edits(), build, "t", count)
    assert len(kept) == 3 and dropped == []


def test_drops_the_longest_edit_only_as_a_last_resort():
    build, count = fake(len(TEX) + 20)
    tex, pdf, kept, dropped = fit_one_page(TEX, edits(), build, "t", count)
    assert [e["id"] for e in dropped] == [1]


def test_every_squeeze_step_changes_the_real_resume():
    for level in range(1, len(SQUEEZE_STEPS) + 1):
        assert squeeze(REAL, level) != squeeze(REAL, level - 1), level


def test_squeeze_keeps_all_text():
    assert squeeze(REAL, len(SQUEEZE_STEPS)).count(r"\resumeItem{") == REAL.count(r"\resumeItem{")
