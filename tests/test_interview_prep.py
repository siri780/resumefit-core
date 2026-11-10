import json

from app.app_emails import apply_emails, classify
from app.interview_prep import Pack, Story, already_sent, find_description, format_pack
from app.scan import connect

INVITE = ("Next steps for your application for Data Scientist, Growth",
          "no-reply@acme.com",
          "Thank you for applying for the Data Scientist, Growth role. We'd like to "
          "schedule an interview with you. Please share your availability.")


def test_invite_is_detected_and_marks_tracker():
    assert classify(INVITE[0], INVITE[2]) == "interview"
    rows = [{"date": "2026-11-01", "company": "Acme", "role": "Data Scientist, Growth",
             "ats_before": "", "ats_after": "", "status": "Applied", "link": "",
             "folder": "", "notes": ""}]
    found = []
    rows, added, rejected = apply_emails(
        rows, [{"date": "2026-11-09", "subject": INVITE[0], "sender": INVITE[1],
                "body": INVITE[2]}], found)
    assert rows[0]["status"] == "Interview" and not added and not rejected
    assert found == [("Acme", "Data Scientist, Growth")]


def test_rejection_wins_over_interview_words():
    body = "After your phone screen, we will not be moving forward with your application."
    assert classify("Update", body) == "rejected"


def test_newsletter_about_interviews_is_ignored():
    found = []
    apply_emails([], [{"date": "2026-11-09", "subject": "5 phone screen tips",
                       "sender": "news@blog.com", "body": "Ace your next phone screen!"}],
                 found)
    assert found == []


def test_pack_uses_real_resume_bullets():
    bullets = ["Ran A/B tests on 14M users with CUPED.", "Built SQL ETL pipelines."]
    pack = Pack(focus=["A/B testing"], technical=["What is a p-value?"],
                behavioral=[Story(question="Tell me about a data project.", bullet_id=0,
                                  tip="Start with the goal."),
                            Story(question="Bad id", bullet_id=9, tip="x")],
                ask_them=["How is success measured?"])
    text = format_pack("Acme", "Data Scientist", "Data Scientist", pack, bullets, True)
    assert "14M users" in text and "Interview Gym" in text
    assert text.count("📌 Use:") == 1          # bad bullet id is skipped, not invented


def test_description_found_from_saved_alert_and_pack_sent_once(tmp_path):
    import app.taps as taps
    con = connect(tmp_path / "t.db")
    taps.remember_alert(con, {"id": "x:1", "company": "Acme", "title": "Data Scientist, Growth",
                              "description": "SQL and experiments"})
    assert find_description(con, "acme", "Data Scientist Growth") == "SQL and experiments"
    assert find_description(con, "Other Co", "Data Scientist") == ""
    assert already_sent(con, "Acme", "DS") is False
    assert already_sent(con, "Acme", "DS") is True
