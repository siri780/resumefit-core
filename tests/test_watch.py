from datetime import timedelta

from app.scan import connect
from app.watch import due


def test_due_only_after_interval(tmp_path):
    con = connect(tmp_path / "t.db")
    every = timedelta(minutes=5)
    assert due(con, "scan", every) is True
    assert due(con, "scan", every) is False
    assert due(con, "scan", timedelta(0)) is True


def test_gmail_warning_once_a_day(tmp_path, monkeypatch):
    from app import watch
    sent = []
    monkeypatch.setattr(watch, "send_message", lambda text, *a: sent.append(text))
    con = connect(tmp_path / "t.db")
    watch.warn_if_gmail_disconnected(con, ["Palantir: ReadTimeout"])
    assert sent == []
    watch.warn_if_gmail_disconnected(con, ["Gmail: RefreshError"])
    watch.warn_if_gmail_disconnected(con, ["Gmail: RefreshError"])
    assert len(sent) == 1 and "Gmail is disconnected" in sent[0]


def test_first_scan_only_once(tmp_path):
    from app.watch import first_scan
    con = connect(tmp_path / "t.db")
    assert first_scan(con) is True
    assert first_scan(con) is False
