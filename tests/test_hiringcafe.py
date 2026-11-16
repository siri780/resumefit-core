import requests

from app import hiringcafe
from app.hiringcafe import fetch_hiringcafe_jobs, hits_from, search_state, to_job

HIT = {"_source": {
    "id": "abc123", "apply_url": "https://boards.greenhouse.io/acme/jobs/1",
    "job_information": {"title": "Data Scientist, New Grad",
                        "description": "<p>Python, SQL, A/B testing</p>"},
    "v5_processed_job_data": {"company_name": "Acme", "formatted_workplace_location": "New York, NY",
                              "estimated_publish_date": "2026-11-15T10:00:00Z"}}}


def test_result_becomes_a_job_with_description():
    job = to_job(HIT)
    assert job["id"] == "Acme:hc-abc123"
    assert (job["company"], job["title"], job["location"]) == \
        ("Acme", "Data Scientist, New Grad", "New York, NY")
    assert job["description"] == "Python, SQL, A/B testing"
    assert job["source"] == "tracker" and job["via"] == "HiringCafe"


def test_unusable_results_are_skipped():
    assert to_job({"job_information": {"title": "Data Scientist"}}) is None    # no company/link


def test_results_found_under_any_key():
    assert hits_from({"results": [1]}) == [1]
    assert hits_from({"hits": {"hits": [2]}}) == [2]
    assert hits_from([3]) == [3]
    assert hits_from({"something": "else"}) == []


def test_search_asks_for_recent_us_full_time_entry_mid_jobs():
    state = search_state("data scientist")
    assert state["searchQuery"] == "data scientist"
    assert state["dateFetchedPastNDays"] == 2
    assert state["commitmentTypes"] == ["Full Time"]
    assert "Entry Level" in state["seniorityLevel"]
    assert state["locations"][0]["formatted_address"] == "United States"


class FakeResponse:
    def __init__(self, status, data=None):
        self.status_code, self._data = status, data

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError("blocked")
            error.response = self
            raise error

    def json(self):
        return self._data


def test_fetch_dedupes_and_survives_being_blocked(monkeypatch):
    calls = []

    def ok_post(self, url, timeout, json):
        calls.append(json["searchState"]["searchQuery"])
        return FakeResponse(200, {"results": [HIT, HIT]})

    monkeypatch.setattr(requests.Session, "post", ok_post)
    jobs, errors = fetch_hiringcafe_jobs()
    assert len(jobs) == 1 and errors == [] and len(calls) == len(hiringcafe.SEARCHES)

    monkeypatch.setattr(requests.Session, "post", lambda self, url, timeout, json: FakeResponse(403))
    jobs, errors = fetch_hiringcafe_jobs()
    assert jobs == [] and errors == ["HiringCafe: HTTPError 403"]


def test_alert_says_hiringcafe():
    from app.notify import format_alert
    text = format_alert({"company": "Acme", "title": "DS", "location": "NY", "tier": "Target",
                         "ats": 80, "missing": [], "score": 70, "sponsorship": "✅",
                         "url": "u", "source": "tracker", "via": "HiringCafe"})
    assert "☕ From HiringCafe" in text


def test_status_message_only_when_it_changes(monkeypatch, tmp_path):
    import sqlite3
    from app import watch
    sent = []
    monkeypatch.setattr(watch, "send_message", lambda text, *a: sent.append(text))
    con = sqlite3.connect(tmp_path / "s.db")
    watch.tell_source_status(con, "HiringCafe", [])
    watch.tell_source_status(con, "HiringCafe", [])
    watch.tell_source_status(con, "HiringCafe", ["HiringCafe: HTTPError 403"])
    watch.tell_source_status(con, "HiringCafe", ["HiringCafe: HTTPError 403"])
    assert len(sent) == 2 and "connected" in sent[0] and "403" in sent[1]


def test_blocked_source_is_remembered(monkeypatch, tmp_path):
    import sqlite3
    from app import watch
    monkeypatch.setattr(watch, "send_message", lambda text, *a: None)
    con = sqlite3.connect(tmp_path / "s.db")
    assert not watch.was_blocked(con, "HiringCafe")
    watch.tell_source_status(con, "HiringCafe", ["HiringCafe: HTTPError 403"])
    assert watch.was_blocked(con, "HiringCafe")
    watch.tell_source_status(con, "HiringCafe", [])
    assert not watch.was_blocked(con, "HiringCafe")
