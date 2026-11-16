import sqlite3
import time

from app import trackers
from app.trackers import age_days, dedupe, describe, from_listings, from_table

NOW = time.time()


def listing(**over):
    item = {"id": "abc", "company_name": "Google", "title": "Software Engineer, New Grad",
            "locations": ["Mountain View, CA"], "url": "https://x.com/job/1?utm_source=Simplify",
            "date_posted": NOW - 3600, "active": True, "is_visible": True,
            "sponsorship": "Other", "category": "Software"}
    item.update(over)
    return item


def test_listings_keep_recent_active_sponsorable_jobs():
    jobs = from_listings("T", [
        listing(),
        listing(id="old", date_posted=NOW - 10 * 86400),
        listing(id="closed", active=False),
        listing(id="hidden", is_visible=False),
        listing(id="citizen", sponsorship="U.S. Citizenship is Required"),
        listing(id="nosponsor", sponsorship="Does Not Offer Sponsorship"),
        listing(id="hw", category="Hardware"),
    ], now=NOW)
    assert [j["id"] for j in jobs] == ["Google:trk-abc"]
    job = jobs[0]
    assert job["url"] == "https://x.com/job/1"          # tracking tag removed
    assert job["source"] == "tracker" and job["via"] == "T"
    assert job["location"] == "Mountain View, CA" and job["description"] == ""


PAGE = """
| Company | Position | Location | Salary | Posting | Age |
|---|---|---|---|---|---|
| <a href="https://www.adobe.com"><strong>Adobe</strong></a> | 2027 University Graduate - Data Scientist | San Jose, CA | $168k/yr | <a href="https://adobe.wd5.myworkdayjobs.com/job/R1"><img src="x" alt="Apply"/></a> | 3d |
| <a href="https://g.com"><strong>Google</strong></a> | Old Role | Seattle, WA | $196k/yr | <a href="https://google.com/jobs/9"><img alt="Apply"/></a> | 9d |
| Company | Position | Location | Posting | Age |
| <a href="https://t.com/"><strong>Triumph Arcade</strong></a> | Data Engineer | San Francisco, CA | <a href="https://jobs.ashbyhq.com/t/1?utm_source=Simplify"><img alt="Apply"/></a> | 5h |
"""


def test_table_rows_parsed_with_or_without_salary_column():
    jobs = from_table("S", PAGE)
    assert [(j["company"], j["title"]) for j in jobs] == [
        ("Adobe", "2027 University Graduate - Data Scientist"),
        ("Triumph Arcade", "Data Engineer")]
    assert jobs[1]["url"] == "https://jobs.ashbyhq.com/t/1"
    assert jobs[0]["location"] == "San Jose, CA"


def test_age_and_dedupe():
    assert (age_days("3d"), age_days("5h"), age_days("2w"), age_days("new")) == (3, 0, 14, None)
    a = {"company": "Adobe", "title": "Data Scientist"}
    b = {"company": "adobe ", "title": "data scientist"}
    assert dedupe([a, b]) == [a]


LONG = "Build models in Python and SQL for product analytics. " * 6


def test_describe_uses_each_job_sites_api(monkeypatch):
    calls = []

    def fake_get_json(url):
        calls.append(url)
        if "greenhouse" in url:
            return {"content": "&lt;p&gt;" + LONG + "&lt;/p&gt;"}
        if "lever" in url:
            return {"descriptionPlain": LONG, "lists": [{"content": "<li>SQL</li>"}]}
        if "myworkdayjobs" in url:
            return {"jobPostingInfo": {"jobDescription": "<p>" + LONG + "</p>"}}
        if "ashbyhq" in url:
            return {"jobs": [{"id": "0d6c5f3e-1111-2222-3333-444455556666", "descriptionPlain": LONG}]}
        if "workable" in url:
            return {"description": LONG, "requirements": "Statistics"}
        if "smartrecruiters" in url:
            return {"jobAd": {"sections": {"jobDescription": {"text": LONG}}}}
        return {}

    monkeypatch.setattr("app.feeds.get_json", fake_get_json)
    urls = [
        "https://job-boards.greenhouse.io/cmt/jobs/8385978",
        "https://jobs.lever.co/esrtreit/9ec61f1b-1eeb-44c8-8be2-f25167b83267/apply",
        "https://adobe.wd5.myworkdayjobs.com/en-US/external_experienced/job/San-Jose/Data-Scientist_R1?src=x",
        "https://jobs.ashbyhq.com/triumph/0d6c5f3e-1111-2222-3333-444455556666",
        "https://apply.workable.com/acme/j/AB12CD34EF/",
        "https://jobs.smartrecruiters.com/Visa/744000098765432-data-scientist",
    ]
    for url in urls:
        job = describe({"url": url, "description": ""})
        assert "Build models in Python" in job["description"], url
    assert calls == [
        "https://boards-api.greenhouse.io/v1/boards/cmt/jobs/8385978",
        "https://api.lever.co/v0/postings/esrtreit/9ec61f1b-1eeb-44c8-8be2-f25167b83267",
        "https://adobe.wd5.myworkdayjobs.com/wday/cxs/adobe/external_experienced/job/San-Jose/Data-Scientist_R1",
        "https://api.ashbyhq.com/posting-api/job-board/triumph",
        "https://apply.workable.com/api/v2/accounts/acme/jobs/AB12CD34EF",
        "https://api.smartrecruiters.com/v1/companies/Visa/postings/744000098765432",
    ]


def test_unknown_site_falls_back_to_reading_the_page(monkeypatch):
    monkeypatch.setattr("app.mail_alerts.add_description",
                        lambda job: {**job, "description": "from page"})
    job = describe({"url": "https://unique.careers.hibob.com/jobs/e59dfdc2", "description": ""})
    assert job["description"] == "from page"


def test_first_tracker_run_is_quiet_then_alerts(monkeypatch, tmp_path):
    from app import scan
    con = scan.connect(tmp_path / "jobs.db")
    con.execute("INSERT INTO seen VALUES ('Acme:1', 'x')")     # watcher already running
    job = {"id": "Adobe:trk-1", "company": "Adobe", "title": "Data Scientist",
           "location": "San Jose, CA", "url": "u", "posted": "", "description": "",
           "source": "tracker", "via": "T"}
    monkeypatch.setattr(trackers, "fetch_tracker_jobs", lambda: ([job], []))
    monkeypatch.setattr(trackers, "describe", lambda j: j)          # page shares nothing
    monkeypatch.setattr(scan, "already_alerted", lambda con, j: False)
    assert scan.scan_trackers(con) == ([], [])                     # first run: saved quietly
    new_job = {**job, "id": "Adobe:trk-2", "title": "Data Scientist II"}
    monkeypatch.setattr(trackers, "fetch_tracker_jobs", lambda: ([job, new_job], []))
    matches, errors = scan.scan_trackers(con)
    assert [m["id"] for m in matches] == ["Adobe:trk-2"]
    assert matches[0]["ats"] is None and matches[0]["via"] == "T"


def test_alert_says_which_tracker():
    from app.notify import format_alert
    text = format_alert({"company": "Adobe", "title": "Data Scientist", "location": "CA",
                         "tier": "Strong", "ats": None, "missing": [], "score": 50,
                         "sponsorship": "❔", "url": "u", "source": "tracker",
                         "via": "SpeedyApply AI/ML"})
    assert "📋 From the SpeedyApply AI/ML tracker" in text


def test_company_feed_skips_job_a_tracker_already_sent(monkeypatch, tmp_path):
    from app import scan
    db = tmp_path / "jobs.db"
    con = scan.connect(db)
    con.execute("INSERT INTO seen VALUES ('Adobe:old', 'x')")
    con.commit()
    job = {"id": "Adobe:R1", "company": "Adobe", "title": "Data Scientist",
           "location": "San Jose, CA", "url": "u", "posted": "", "description": "Python SQL"}
    monkeypatch.setattr(scan, "DB", db)
    monkeypatch.setattr(scan, "connect", lambda path=db: sqlite3.connect(path))
    monkeypatch.setattr(scan, "fetch_all", lambda include_workday=True: ([job], []))
    monkeypatch.setattr(scan, "already_alerted", lambda con, j: True)
    looked_up = []
    monkeypatch.setattr(scan, "job_description", lambda j: looked_up.append(j))
    matches, errors, total = scan.scan()
    assert matches == [] and looked_up == []


ROWS = [{"company": "Amazon", "role": "Data Scientist III (ID: 10591731)"},
        {"company": "Twosigma", "role": "Quantitative Researcher: Machine Learning"},
        {"company": "Databricks", "role": "Software Engineer - New Grad (2027 Start)"},
        {"company": "Mastercard", "role": "Data Scientist"},
        {"company": "Robinhood", "role": "(role not in email)"}]


def test_already_applied_jobs_are_recognised():
    from app.applications import applied_before, applied_keys
    keys = applied_keys(ROWS)
    yes = [("Amazon", "Data Scientist III"), ("Two Sigma", "Quantitative Researcher - Machine Learning"),
           ("Databricks", "Software Engineer - New Grad")]
    no = [("Amazon", "Data Scientist II"), ("Mastercard", "Senior Data Scientist"),
          ("Robinhood", "Data Scientist"), ("Adobe", "Data Scientist")]
    assert all(applied_before({"company": c, "title": t}, keys) for c, t in yes)
    assert not any(applied_before({"company": c, "title": t}, keys) for c, t in no)


def test_watcher_drops_applied_jobs(monkeypatch):
    from app import applications, watch
    monkeypatch.setattr(applications, "read_tracker", lambda: ROWS)
    monkeypatch.setattr("app.backup.restore", lambda: None)
    monkeypatch.setattr("app.backup.refresh", lambda every_seconds=300: None)
    jobs = [{"company": "Amazon", "title": "Data Scientist III"},
            {"company": "Amazon", "title": "Data Scientist II"}]
    assert watch.skip_applied(jobs) == [jobs[1]]
