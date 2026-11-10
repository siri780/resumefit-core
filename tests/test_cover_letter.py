import app.taps as taps
from app.ats import load_skills
from app.cover_letter import check_letter
from app.scan import connect

RESUME = ("Built a Python and SQL pipeline that raised ATS match from 65% to 73%. "
          "Ran A/B tests on 13 million users with CUPED.")


def test_cover_button_on_alerts_with_a_description(tmp_path):
    con = connect(tmp_path / "t.db")
    rows = taps.remember_alert(con, {"id": "x:1", "company": "Acme", "title": "DS",
                                     "description": "SQL"})
    labels = [b["text"] for row in rows for b in row]
    assert labels == ["✨ Tailor my resume", "✉️ Cover letter", "🔕 Pause company"]
    data = rows[0][1]["callback_data"]
    assert data.startswith(taps.COVER_PREFIX) and len(data.encode()) <= 64


def test_guard_removes_invented_numbers_and_skills():
    skills = load_skills()
    allowed = {"Python", "SQL", "A/B Testing"}
    paragraphs = ["I raised ATS match from 65% to 73% with Python. "
                  "I also cut costs by 40%.",
                  "I ran A/B tests on 13 million users. I am an expert in Kubernetes."]
    kept, removed = check_letter(paragraphs, RESUME, allowed, skills)
    text = " ".join(kept)
    assert "65%" in text and "13 million" in text
    assert "40%" not in text and "Kubernetes" not in text
    assert len(removed) == 2


def test_graduation_year_is_allowed():
    kept, removed = check_letter(["I graduate in May 2027."], RESUME, set(), load_skills())
    assert kept == ["I graduate in May 2027."] and removed == []


def test_long_letter_is_trimmed():
    para = "I like data work and clear writing. " * 60
    kept, _ = check_letter([para, para], RESUME, set(), load_skills())
    assert sum(len(p.split()) for p in kept) <= 260


def test_cover_tap_sends_letter(monkeypatch, tmp_path):
    con = connect(tmp_path / "t.db")
    rows = taps.remember_alert(con, {"id": "x:1", "company": "Acme", "title": "DS",
                                     "base": "Data Scientist", "description": "SQL"})
    sent = []
    monkeypatch.setattr(taps, "telegram", lambda method, **k: {"ok": True})
    monkeypatch.setattr(taps, "send_message", lambda text, *a: sent.append(text) or {"ok": True})
    monkeypatch.setattr("app.cover_letter.write_letter",
                        lambda job, tex: ("Dear Acme Hiring Team,\n\nHello.", []))
    monkeypatch.setattr(taps, "get_taps", lambda: (
        [{"update_id": 1}], [{"id": "q1", "data": rows[0][1]["callback_data"]}]))
    assert taps.process_taps(con) == 0          # a letter isn't a tailored resume
    assert "Cover letter" in sent[0] and "Dear Acme Hiring Team" in sent[1]
