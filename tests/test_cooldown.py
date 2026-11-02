from datetime import timedelta

from app import cooldown
from app.scan import connect


def rows(company, n, days_ago=1):
    day = (cooldown.today() - timedelta(days=days_ago)).isoformat()
    return [{"date": day, "company": company, "role": f"Role {i}"} for i in range(n)]


def test_names_match_loosely():
    assert cooldown.norm("Capital One, Inc.") == cooldown.norm("capital one")
    assert cooldown.norm("Salesforce") != cooldown.norm("Salesforce Ventures")


def test_auto_pause_after_three_recent_applications(tmp_path):
    con = connect(tmp_path / "t.db")
    newly = cooldown.auto_pause(con, rows("Salesforce", 3) + rows("Stripe", 2)
                                + rows("Old Co", 5, days_ago=45))
    assert [n for n, _ in newly] == ["Salesforce"]
    assert cooldown.is_paused(con, "salesforce, inc.")
    assert not cooldown.is_paused(con, "Stripe")
    assert not cooldown.is_paused(con, "Old Co")      # applications too old
    assert cooldown.auto_pause(con, rows("Salesforce", 4)) == []   # already paused


def test_manual_pause_and_expiry(tmp_path):
    con = connect(tmp_path / "t.db")
    until = cooldown.pause(con, "Google", days=60)
    assert cooldown.is_paused(con, "Google") == until
    assert cooldown.paused_now(con) == [("Google", until)]
    cooldown.pause(con, "Meta", days=-1)               # already ended
    assert not cooldown.is_paused(con, "Meta")
    # A shorter pause never cuts an existing longer one short
    assert cooldown.pause(con, "Google", days=5) == until


def test_add_companies_keeps_first_working_board(monkeypatch):
    from app import add_companies

    def fake(company, slug):
        if slug == "good":
            return [{"id": 1}]
        raise ValueError("404")

    monkeypatch.setitem(add_companies.READERS, "greenhouse", fake)
    assert add_companies.try_candidate("X", "greenhouse", ["bad", "good"]) == ("good", 1)
    assert add_companies.try_candidate("X", "greenhouse", ["bad"]) is None
