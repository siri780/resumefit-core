import app.taps as taps
from app.scan import connect


def test_alert_round_trip(tmp_path):
    con = connect(tmp_path / "t.db")
    match = {"id": "greenhouse:acme:1", "company": "Acme", "title": "ML Engineer",
             "location": "NY", "url": "https://x", "base": "ML Engineer",
             "description": "Python and PyTorch"}
    buttons = taps.remember_alert(con, match)
    data = buttons[0][0]["callback_data"]
    assert data.startswith(taps.BUTTON_PREFIX) and len(data.encode()) <= 64
    job = taps.find_alert(con, data[len(taps.BUTTON_PREFIX):])
    assert job["company"] == "Acme" and job["base"] == "ML Engineer"


def test_only_my_taps_are_handled(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    updates = [
        {"update_id": 1, "callback_query": {"id": "a", "data": "t:abc",
                                            "message": {"chat": {"id": 42}}}},
        {"update_id": 2, "callback_query": {"id": "b", "data": "t:abc",
                                            "message": {"chat": {"id": 99}}}},
        {"update_id": 3, "callback_query": {"id": "c", "data": "other",
                                            "message": {"chat": {"id": 42}}}},
    ]
    monkeypatch.setattr(taps, "telegram",
                        lambda method, **kw: {"ok": True, "result": updates})
    _, mine = taps.get_taps()
    assert [q["id"] for q in mine] == ["a"]


def test_process_taps_tailors_and_confirms(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    con = connect(tmp_path / "t.db")
    key = taps.remember_alert(con, {"id": "x:1", "company": "Acme",
                                    "title": "DS", "url": "u", "base": "Data Scientist",
                                    "description": "SQL"})[0][0]["callback_data"]
    calls, tailored = [], []
    update = {"update_id": 7, "callback_query": {
        "id": "q", "data": key, "message": {"chat": {"id": 42}}}}

    def fake(method, **kw):
        calls.append((method, kw))
        return {"ok": True, "result": [update]}

    monkeypatch.setattr(taps, "telegram", fake)
    monkeypatch.setattr(taps, "tailor_job", lambda job: tailored.append(job))
    assert taps.process_taps(con) == 1
    assert tailored[0]["company"] == "Acme"
    assert ("getUpdates", {"offset": 8, "limit": 1, "timeout": 0}) in calls


def test_edits_message_lists_before_and_after():
    job = {"company": "Acme", "title": "DS", "base": "Data Scientist", "url": "u"}
    msg = taps.edits_message(job, {"percent": 60, "missing": []},
                             {"percent": 70, "missing": ["Spark"]},
                             [{"original": "Did 40\\% work", "new": "Drove 40\\% work"}], 1)
    assert "60% → 70%" in msg and "Drove 40% work" in msg
    assert "1 suggestion(s) blocked" in msg and "Spark" in msg


def test_chat_id_with_stray_whitespace_still_matches(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", " 42\n")
    updates = [{"update_id": 1, "callback_query": {
        "id": "a", "data": "t:abc", "message": {"chat": {"id": 42}}}}]
    monkeypatch.setattr(taps, "telegram",
                        lambda method, **kw: {"ok": True, "result": updates})
    assert [q["id"] for q in taps.get_taps()[1]] == ["a"]


def test_network_error_does_not_crash(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")

    def boom(*a, **k):
        raise taps.requests.ConnectionError("down")

    monkeypatch.setattr(taps.requests, "post", boom)
    monkeypatch.setattr(taps.time, "sleep", lambda s: None)
    assert taps.telegram("getUpdates")["ok"] is False


def test_dropped_connection_is_retried_with_whole_file(monkeypatch, tmp_path):
    import io
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setattr(taps.time, "sleep", lambda s: None)
    calls = []

    class OK:
        def json(self):
            return {"ok": True}

    def flaky(url, data=None, files=None, **k):
        calls.append(files["document"][1].read())
        if len(calls) == 1:
            raise taps.requests.ConnectionError("reset by peer")
        return OK()

    monkeypatch.setattr(taps.requests, "post", flaky)
    f = io.BytesIO(b"%PDF-1.5 resume")
    assert taps.telegram("sendDocument", files={"document": ("r.pdf", f)})["ok"]
    assert calls == [b"%PDF-1.5 resume", b"%PDF-1.5 resume"]


def test_pause_button_pauses_company(monkeypatch, tmp_path):
    from app import cooldown
    from app.scan import connect
    con = connect(tmp_path / "t.db")
    buttons = taps.remember_alert(con, {"id": "x:1", "company": "Capital One",
                                        "title": "DS", "description": ""})
    labels = [b["text"] for b in buttons[0]]
    assert labels == ["🔕 Pause company"]               # no description: no Tailor
    pause_data = buttons[0][0]["callback_data"]
    sent = []
    monkeypatch.setattr(taps, "telegram", lambda method, **k: {"ok": True})
    monkeypatch.setattr(taps, "send_message", lambda text, *a: sent.append(text))
    monkeypatch.setattr(taps, "get_taps", lambda: (
        [{"update_id": 1}], [{"id": "q1", "data": pause_data}]))
    assert taps.process_taps(con) == 0                  # nothing tailored
    assert cooldown.is_paused(con, "capital one")
    assert "Capital One" in sent[0]
