"""New-grad jobs from community GitHub trackers.

These lists are updated many times a day by people who watch hundreds of
company career sites, so they catch new-grad roles (FAANG, AI labs, quant
firms) that job boards miss. They only give a title and a link, so the
description is fetched from the job page afterwards.
"""
import html
import re
import time
from datetime import datetime, timezone

import requests

from app.feeds import HEADERS, TIMEOUT, make_job

RAW = "https://raw.githubusercontent.com/"
JSON_TRACKERS = {      # name: listings file (the same format for both)
    "SimplifyJobs New Grad": RAW + "SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json",
    "New Grad 2027": RAW + "vanshb03/New-Grad-2027/dev/.github/scripts/listings.json",
}
TABLE_TRACKERS = {     # name: markdown page with job tables
    "SpeedyApply AI/ML": RAW + "speedyapply/2027-AI-College-Jobs/main/NEW_GRAD_USA.md",
    "SpeedyApply SWE": RAW + "speedyapply/2027-SWE-College-Jobs/main/NEW_GRAD_USA.md",
}
MAX_AGE_DAYS = 3
SKIP_CATEGORIES = {"hardware"}
NO_SPONSOR = {"does not offer sponsorship", "u.s. citizenship is required"}

ROW = re.compile(r"^\|(.+)\|\s*$")
LINK = re.compile(r'href="([^"]+)"')
AGE = re.compile(r"^(\d+)\s*([mhdw])$", re.I)


def _get(url):
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT * 3)
    response.raise_for_status()
    return response


def _text(cell):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", cell))).strip()


def _strip_tracking(url):
    return re.sub(r"[?&]utm_source=[^&]*", "", url).rstrip("?&")


def from_listings(name, listings, now=None):
    """Recent, active, sponsorship-possible jobs from a listings.json file."""
    now = now or time.time()
    jobs = []
    for item in listings:
        if not item.get("active") or not item.get("is_visible", True):
            continue
        if now - item.get("date_posted", 0) > MAX_AGE_DAYS * 86400:
            continue
        if (item.get("category") or "").lower() in SKIP_CATEGORIES:
            continue
        if (item.get("sponsorship") or "").lower() in NO_SPONSOR:
            continue
        posted = datetime.fromtimestamp(item["date_posted"], timezone.utc)
        job = make_job(item["company_name"], f"trk-{item['id']}", item["title"],
                       "; ".join(item.get("locations") or []),
                       _strip_tracking(item["url"]), posted.isoformat(), "")
        jobs.append({**job, "source": "tracker", "via": name})
    return jobs


def age_days(text):
    """'3d' -> 3, '5h' -> 0, '2w' -> 14; None if it can't be read."""
    m = AGE.match(text.strip())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    return {"m": 0, "h": 0, "d": n, "w": 7 * n}[unit]


def from_table(name, page):
    """Recent jobs from a SpeedyApply markdown page."""
    jobs = []
    for line in page.splitlines():
        m = ROW.match(line)
        if not m or "<strong>" not in line and "href" not in line:
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if len(cells) < 5:
            continue
        age = age_days(cells[-1])
        links = LINK.findall(cells[-2])
        if age is None or age > MAX_AGE_DAYS or not links:
            continue
        company, title, location = _text(cells[0]), _text(cells[1]), _text(cells[2])
        url = _strip_tracking(html.unescape(links[-1]))
        job_id = "trk-" + re.sub(r"\W+", "-", url.split("//", 1)[-1])[-80:]
        job = make_job(company, job_id, title, location, url, "", "")
        jobs.append({**job, "source": "tracker", "via": name})
    return jobs


GREENHOUSE_URL = re.compile(r"greenhouse\.io/(?:embed/job_app\?for=)?([\w-]+)/jobs/(\d+)")
GREENHOUSE_EMBED = re.compile(r"greenhouse\.io/embed/job_app\?.*?for=([\w-]+).*?token=(\d+)")
LEVER_URL = re.compile(r"jobs\.lever\.co/([\w.-]+)/([0-9a-f-]{36})")


def describe(job):
    """Fill in the description: company job APIs first, then the page itself."""
    from app.feeds import clean, get_json
    from app.mail_alerts import add_description
    url = job["url"]
    try:
        m = GREENHOUSE_URL.search(url) or GREENHOUSE_EMBED.search(url)
        if m:
            data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{m.group(1)}/jobs/{m.group(2)}")
            job["description"] = clean(data.get("content"))
            return job
        m = LEVER_URL.search(url)
        if m:
            data = get_json(f"https://api.lever.co/v0/postings/{m.group(1)}/{m.group(2)}")
            extra = " ".join(i.get("content", "") for i in data.get("lists", []))
            job["description"] = clean(data.get("descriptionPlain", "") + " " + extra)
            return job
    except Exception:
        pass                                   # fall back to reading the page
    return add_description(job)


def dedupe(jobs):
    """The same role is often on several trackers: keep the first."""
    seen, out = set(), []
    for job in jobs:
        key = (job["company"].strip().lower(), job["title"].strip().lower())
        if key not in seen:
            seen.add(key)
            out.append(job)
    return out


def fetch_tracker_jobs():
    """Returns (jobs, errors)."""
    jobs, errors = [], []
    for name, url in JSON_TRACKERS.items():
        try:
            jobs += from_listings(name, _get(url).json())
        except Exception as error:
            errors.append(f"{name}: {type(error).__name__}")
    for name, url in TABLE_TRACKERS.items():
        try:
            jobs += from_table(name, _get(url).text)
        except Exception as error:
            errors.append(f"{name}: {type(error).__name__}")
    return dedupe(jobs), errors


if __name__ == "__main__":
    found, problems = fetch_tracker_jobs()
    print(f"{len(found)} recent new-grad jobs · errors: {problems or 'none'}")
    for j in found[:15]:
        print(f"  [{j['via']}] {j['company']} – {j['title']} ({j['location']})")
