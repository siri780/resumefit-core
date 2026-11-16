import sqlite3

from app import h1b
from app.h1b import history, norm, refresh, totals_from_csv

OLD_FORMAT = """Fiscal Year,Employer,Initial Approval,Initial Denial,Continuing Approval,Continuing Denial,NAICS,Tax ID,State,City,ZIP
2023,"AMAZON.COM SERVICES LLC","2,000",10,"1,500",5,45,1,WA,SEATTLE,98109
2023,AMAZON WEB SERVICES INC,300,1,200,1,51,2,WA,SEATTLE,98109
2023,ADOBE INC,400,2,600,3,51,3,CA,SAN JOSE,95110
2023,AIR PRODUCTS AND CHEMICALS INC,50,0,30,0,32,4,PA,ALLENTOWN,18195
2023,TINY STARTUP LLC,1,0,0,0,54,5,NY,NEW YORK,10001
"""

NEW_FORMAT = """﻿Fiscal Year,Employer (Petitioner) Name,Tax ID,Industry (NAICS) Code,Petitioner City,Petitioner State,Petitioner Zip Code,New Employment Approval,New Employment Denial,Continuation Approval,Continuation Denial,Change with Same Employer Approval,Change with Same Employer Denial,New Concurrent Approval,New Concurrent Denial,Change of Employer Approval,Change of Employer Denial,Amended Approval,Amended Denial
2025,"GOOGLE LLC",1,51,MOUNTAIN VIEW,CA,94043,"1,000",5,800,2,100,0,10,0,200,1,50,0
"""


def test_names_normalised():
    assert norm("Amazon.com Services, LLC") == "amazon com services"
    assert norm("Adobe Inc.") == "adobe"
    assert norm("Johnson & Johnson") == "johnson and johnson"


def test_both_uscis_file_formats_read():
    totals, year = totals_from_csv(OLD_FORMAT)
    assert totals["amazon com services"] == 3500 and totals["adobe"] == 1000 and year == 2023
    totals, year = totals_from_csv(NEW_FORMAT)
    assert totals["google"] == 2160 and year == 2025


def test_company_lookup():
    table = {"amazon com services": (3500, 2023), "amazon web services": (500, 2023),
             "adobe": (1000, 2023), "air products and chemicals": (80, 2023),
             "meta platforms": (5000, 2023), "anthropic pbc": (60, 2023)}
    assert history("Adobe", table) == (1000, 2023)
    assert history("Amazon", table) == (4000, 2023)        # all Amazon entities
    assert history("AIR", table) is None                   # too short to guess
    assert history("Meta", table) == (5000, 2023)
    assert history("Anthropic", table) == (60, 2023)
    assert history("Robinhood", table) is None


def test_refresh_saves_totals_and_reports_failure(monkeypatch, tmp_path):
    con = sqlite3.connect(tmp_path / "j.db")

    class Resp:
        def __init__(self, ok, body=b""):
            self.ok, self.content, self.status_code = ok, body, 200 if ok else 404

        def raise_for_status(self):
            if not self.ok:
                import requests
                error = requests.HTTPError("x")
                error.response = self
                raise error

    monkeypatch.setattr(h1b.requests, "get",
                        lambda url, **kw: Resp("2023" in url, OLD_FORMAT.encode()))
    assert refresh(con) == []
    rows = dict(con.execute("SELECT name, approvals FROM h1b"))
    assert rows["adobe"] == 1000 and "tiny startup" not in rows    # < 10 approvals dropped
    monkeypatch.setattr(h1b.requests, "get", lambda url, **kw: Resp(False))
    assert refresh(con) == ["H-1B data: HTTPError 404"]
    assert con.execute("SELECT COUNT(*) FROM h1b").fetchone()[0] > 0   # old data kept


def test_alert_uses_sponsor_history(monkeypatch):
    from app import rank
    monkeypatch.setattr(h1b, "_cache", {"adobe": (1000, 2023)})
    job = {"company": "Adobe", "title": "Data Scientist", "location": "San Jose, CA",
           "description": "python sql statistics"}
    result = rank.assess(job, 80)
    assert result["sponsorship"] == "🟢 not mentioned, but Adobe had 1,000 H-1B approvals (FY2023)"
    other = rank.assess({**job, "company": "Tiny Startup"}, 80)
    assert other["sponsorship"] == "❔ not mentioned" and result["score"] > other["score"]
