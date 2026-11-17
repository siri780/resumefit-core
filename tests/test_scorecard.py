import sqlite3
from datetime import date, datetime

from app import scorecard
from app.scorecard import maybe_send_scorecard, scorecard_text, tracker_stats, week_bounds
from app.summary import record_alert

SUNDAY = date(2026, 11, 22)
ROWS = [
    {"date": "2026-11-16", "company": "Amazon", "role": "SDE", "status": "Applied",
     "notes": "Logged from email; referral from Likhith"},
    {"date": "2026-11-18", "company": "Adobe", "role": "DS", "status": "Interview", "notes": ""},
    {"date": "2026-11-20", "company": "Adobe", "role": "MLE", "status": "Applied", "notes": ""},
    {"date": "2026-10-28", "company": "Reddit", "role": "DS", "status": "Rejected",
     "notes": "Logged from email; Rejection email 2026-11-19"},
    {"date": "2026-10-28", "company": "Fidelity", "role": "DS", "status": "Rejected",
     "notes": "Rejection email 2026-10-30"},
]


def test_week_runs_monday_to_sunday():
    assert week_bounds(SUNDAY) == ("2026-11-16", "2026-11-22")
    assert week_bounds(date(2026, 11, 18)) == ("2026-11-16", "2026-11-22")


def test_tracker_numbers():
    t = tracker_stats(ROWS, "2026-11-16", "2026-11-22")
    assert (t["apps_week"], t["apps_total"], t["companies_week"]) == (3, 5, 2)
    assert (t["rejected_week"], t["rejected_total"]) == (1, 2)
    assert (t["interviews"], t["offers"]) == (1, 0)
    assert (t["referrals_week"], t["referrals_total"]) == (1, 1)


def test_scorecard_text_with_sources(monkeypatch, tmp_path):
    con = sqlite3.connect(tmp_path / "s.db")
    monkeypatch.setattr("app.summary.today", lambda: "2026-11-20")
    record_alert(con, {"company": "A", "title": "DS", "url": "u", "source": "tracker",
                       "via": "SimplifyJobs New Grad"})
    record_alert(con, {"company": "B", "title": "DS", "url": "u"})
    record_alert(con, {"company": "C", "title": "DS", "url": "u"})
    text = scorecard_text(con, ROWS, SUNDAY)
    assert "Nov 16 – Nov 22" in text
    assert "Matching roles found: 3" in text
    assert "Applications: 3 this week (2 companies)" in text
    assert "company sites 2, SimplifyJobs New Grad 1" in text
    assert "Reply rate (any answer): 60%" in text           # 2 rejections + 1 interview of 5
    assert "5/20 strong applications: too early" in text


def test_sent_once_on_sunday_evening(monkeypatch, tmp_path):
    con = sqlite3.connect(tmp_path / "s.db")
    sent = []

    class Clock(datetime):
        now_value = datetime(2026, 11, 22, 18, 30)

        @classmethod
        def now(cls, tz=None):
            return cls.now_value

    monkeypatch.setattr(scorecard, "datetime", Clock)
    assert maybe_send_scorecard(con, sent.append, lambda: ROWS)
    assert not maybe_send_scorecard(con, sent.append, lambda: ROWS)    # once per Sunday
    Clock.now_value = datetime(2026, 11, 23, 19, 0)                     # Monday
    assert not maybe_send_scorecard(con, sent.append, lambda: ROWS)
    assert len(sent) == 1 and "Weekly scorecard" in sent[0]
