import app.feeds as feeds


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


def test_amazon_reader(monkeypatch):
    job = {"id_icims": "123", "title": "Data Scientist I",
           "normalized_location": "Bellevue, Washington, USA",
           "job_path": "/en/jobs/123/data-scientist", "posted_date": "October 23, 2026",
           "description": "Build models.", "basic_qualifications": "- SQL",
           "preferred_qualifications": "- Python"}
    monkeypatch.setattr(feeds.requests, "get",
                        lambda *a, **k: FakeResponse({"jobs": [job]}))
    jobs = feeds.amazon("Amazon")
    assert len(jobs) == 1  # same job from every search is kept once
    j = jobs[0]
    assert j["id"] == "Amazon:123"
    assert j["url"] == "https://www.amazon.jobs/en/jobs/123/data-scientist"
    assert "SQL" in j["description"] and "Python" in j["description"]
    assert j["location"] == "Bellevue, Washington, USA"


def test_slow_sources_skipped_between_big_scans(monkeypatch):
    monkeypatch.setattr(feeds, "load_companies", lambda: [
        {"company": "Amazon", "source": "amazon", "slug": ""},
        {"company": "X", "source": "greenhouse", "slug": "x"}])
    called = []
    monkeypatch.setitem(feeds.READERS, "amazon", lambda c, s: called.append(c) or [])
    monkeypatch.setitem(feeds.READERS, "greenhouse", lambda c, s: called.append(c) or [])
    feeds.fetch_all(include_workday=False)
    assert called == ["X"]


def test_workday_skips_half_empty_entries(monkeypatch):
    class Resp(FakeResponse):
        pass

    posts = {"jobPostings": [{"title": "Data Scientist", "externalPath": "/job/1",
                              "locationsText": "Santa Clara, CA"},
                             {"externalPath": "/job/2"}, {"title": "No path"}]}
    monkeypatch.setattr(feeds.requests, "post", lambda *a, **k: Resp(posts))
    jobs = feeds.workday("Intel", "https://intel.wd1.myworkdayjobs.com/External")
    assert [j["id"] for j in jobs] == ["Intel:/job/1"]


# ---------- Google and Microsoft (shapes copied from their real responses) ----------
def _google_page():
    import json
    entry = ["135323144725373638", "Data Scientist", "https://signin",
             [None, "<ul><li>Use SQL and Python.</li></ul>"],
             [None, "<h3>Minimum qualifications:</h3><ul><li>Master's degree.</li></ul>"],
             "projects/x", None, "Google", "en-US",
             [["San Bruno, CA, USA", ["San Bruno, CA, USA"], "San Bruno", None, "CA", "US"],
              ["New York, NY, USA", ["New York, NY, USA"], "New York", None, "NY", "US"]],
             [None, "<p>At YouTube, we believe...</p>"], [3, 4],
             [1791821337, 278000000]]
    data = json.dumps([[entry], None, 819, 20])
    return ("<script>AF_initDataCallback({key: 'ds:1', hash: '2', data:" + data +
            ", sideChannel: {}});</script>")


def test_google_page_parsing():
    from app.feeds import google_jobs_from_page
    (job,) = google_jobs_from_page(_google_page())
    assert job["id"] == "Google:135323144725373638"
    assert job["title"] == "Data Scientist"
    assert job["location"] == "San Bruno, CA, USA; New York, NY, USA"
    assert job["url"].endswith("/jobs/results/135323144725373638")
    assert "Use SQL and Python" in job["description"]
    assert "Master's degree" in job["description"]
    assert job["posted"].startswith("2026-")


def test_microsoft_search_and_lazy_description():
    from app import feeds

    class R:
        status_code = 200

        def __init__(self, data):
            self.ok, self._data = True, data

        def json(self):
            return self._data

        def raise_for_status(self):
            pass

    def fake_get(url, params=None, **k):
        if url.endswith("search"):
            if params["start"] == 0 and params["query"] == "data scientist":
                return R({"data": {"positions": [{
                    "id": 1970393556988108, "name": "Data Scientist, Product Analytics",
                    "locations": ["United States, Washington, Redmond"],
                    "postedTs": 1792595911}]}})
            return R({"data": {"positions": []}})
        return R({"data": {"jobDescription": "<b>Overview</b><p>A/B tests and SQL.</p>"}})

    old, old_sleep = feeds.requests.get, feeds.time.sleep
    feeds.requests.get = fake_get
    feeds.time.sleep = lambda s: None
    try:
        (job,) = feeds.microsoft("Microsoft")
        assert job["id"] == "Microsoft:1970393556988108"
        assert job["url"] == "https://apply.careers.microsoft.com/careers/job/1970393556988108"
        assert job["location"] == "United States, Washington, Redmond"
        assert job["description"] == ""
        assert feeds.job_description(job) == "Overview A/B tests and SQL."
    finally:
        feeds.requests.get, feeds.time.sleep = old, old_sleep


def test_microsoft_rate_limit_keeps_going_next_run():
    from app import feeds

    class R:
        status_code = 429

    old, old_sleep = feeds.requests.get, feeds.time.sleep
    feeds.requests.get = lambda *a, **k: R()
    feeds.time.sleep = lambda s: None
    try:
        assert feeds.microsoft("Microsoft") == []
    finally:
        feeds.requests.get, feeds.time.sleep = old, old_sleep


# ---------- Apple (shape copied from the real search page) ----------
def _apple_page(results):
    import json
    data = {"loaderData": {"root": {}, "search": {"searchResults": results, "totalRecords": len(results)}}}
    return ("<script>window.__staticRouterHydrationData = JSON.parse(" +
            json.dumps(json.dumps(data)) + ");</script>")


APPLE_JOB = {"id": "200692043-2459", "jobSummary": "Build ML platform features.",
             "locations": [{"name": "New York City", "countryName": "United States of America"}],
             "postingTitle": "ML Engineer - Ads", "postDateInGMT": "2026-11-03T11:19:00.863Z",
             "transformedPostingTitle": "ml-engineer-ads", "postExternal": True}


def test_apple_search_page():
    from app.feeds import apple_jobs_from_page
    hidden = dict(APPLE_JOB, id="1-1", postExternal=False)
    (job,) = apple_jobs_from_page(_apple_page([APPLE_JOB, hidden]))
    assert job["id"] == "Apple:200692043-2459"
    assert job["location"] == "New York City, United States of America"
    assert job["url"] == "https://jobs.apple.com/en-us/details/200692043-2459/ml-engineer-ads"
    assert job["description"] == "Build ML platform features."


def test_apple_full_description_fetched_once(monkeypatch):
    from app import feeds
    (job,) = feeds.apple_jobs_from_page(_apple_page([APPLE_JOB]))

    class R:
        ok = True
        text = _apple_page([dict(APPLE_JOB, description="Long description here.",
                                 minimumQualifications="SQL and Python.")])

    calls = []
    monkeypatch.setattr(feeds.requests, "get", lambda *a, **k: calls.append(1) or R())
    text = feeds.job_description(job)
    assert "SQL and Python" in text and "Long description" in text
    feeds.job_description(job)
    assert len(calls) == 1
