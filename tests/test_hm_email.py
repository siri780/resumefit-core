from types import SimpleNamespace

from app import hm_email, taps
from app.hm_email import people_search, write_email
from app.scan import connect

TEX = r"""\section{Projects} \item Built a movie recommender in Python and SQL; HitRate@10 rose from 1.4\% to 13.5\%."""


def fake_draft(subject, paragraphs):
    return lambda resume, jd, company, title: SimpleNamespace(subject=subject, paragraphs=paragraphs)


def test_email_has_links_and_guard_removes_made_up_facts(monkeypatch):
    monkeypatch.setattr(hm_email, "draft", fake_draft("Data Scientist role at Acme", [
        "I'm Shirisha, an MS Data Science student at Stony Brook graduating in May 2027, and I applied for your Data Scientist role.",
        "I built a recommender that raised HitRate@10 from 1.4% to 13.5%. I also cut costs by 40% at a bank.",
        "Would you be open to a quick chat?"]))
    job = {"company": "Acme", "title": "Data Scientist", "description": "Python SQL"}
    subject, text, removed = write_email(job, TEX, "Data Scientist")
    assert subject == "Data Scientist role at Acme"
    assert text.startswith("Hi [Name],") and text.endswith("Thank you,\nShirisha Gajendra")
    assert "13.5%" in text and "40%" not in text and len(removed) == 1
    assert "github.com/siri780/ab-test-criteo-uplift" in text and "siri780.github.io" in text


def test_links_match_the_role():
    assert "medical-text-router" in str(hm_email.PROOF["ML Engineer"])
    assert "resumefit" in str(hm_email.PROOF["Software Engineer"])
    assert people_search("Two Sigma", "Data Scientist").endswith("keywords=Two+Sigma+data+science+manager")


def test_alert_has_email_button_and_tap_sends_draft(monkeypatch, tmp_path):
    con = connect(tmp_path / "t.db")
    rows = taps.remember_alert(con, {"id": "x:1", "company": "Acme", "title": "DS",
                                     "base": "Data Scientist", "description": "SQL"})
    email_button = rows[1][0]
    assert email_button["text"] == "📨 Hiring-manager email"
    sent = []
    monkeypatch.setattr(taps, "telegram", lambda method, **k: {"ok": True})
    monkeypatch.setattr(taps, "send_message", lambda text, *a: sent.append(text) or {"ok": True})
    monkeypatch.setattr("app.hm_email.write_email",
                        lambda job, tex, base: ("DS at Acme", "Hi [Name],\n\nHello.", []))
    monkeypatch.setattr(taps, "get_taps", lambda: (
        [{"update_id": 1}], [{"id": "q1", "data": email_button["callback_data"]}]))
    assert taps.process_taps(con) == 0
    assert "Hiring-manager email · Acme" in sent[0] and "linkedin.com/search" in sent[0]
    assert "Subject:</b> DS at Acme" in sent[1]


def test_email_taps_are_read_and_dont_need_latex(monkeypatch):
    monkeypatch.setattr(taps, "my_chat", lambda: "1")
    monkeypatch.setattr(taps, "telegram", lambda method, **k: {"ok": True, "result": [
        {"update_id": 5, "callback_query": {"id": "q", "data": taps.EMAIL_PREFIX + "k",
                                            "message": {"chat": {"id": 1}}}}]})
    updates, found = taps.get_taps()
    assert [q["data"] for q in found] == [taps.EMAIL_PREFIX + "k"]
    assert not taps.has_taps()
