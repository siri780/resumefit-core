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


PREFIX = re.compile(r"^\s*(?:new grad(?:uate)?(?:\s*20\d\d)?|20\d\d new grad|early careers?)\s*:\s*", re.I)


def clean_title(title):
    """'New Grad 2027: Quantitative Researcher' -> 'Quantitative Researcher'."""
    return PREFIX.sub("", title).strip() or title


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
WORKDAY_URL = re.compile(r"https://([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/?#]+)(/job/[^?#]+)")
ASHBY_URL = re.compile(r"jobs\.ashbyhq\.com/([^/?#]+)/([0-9a-f-]{36})")
WORKABLE_URL = re.compile(r"apply\.workable\.com/([^/?#]+)/j/([0-9A-Z]+)", re.I)
SMARTRECRUITERS_URL = re.compile(r"jobs\.smartrecruiters\.com/([^/?#]+)/(\d+)")
BAMBOO_URL = re.compile(r"https://([\w-]+)\.bamboohr\.com/careers/(\d+)")
RIPPLING_URL = re.compile(r"ats\.rippling\.com/([^/?#]+)/jobs/([0-9a-f-]{36})")
SHORT_LINK = re.compile(r"https?://(?:go\.vansh\.nyc|lnkd\.in|bit\.ly|tinyurl\.com)/", re.I)
ORACLE_URL = re.compile(r"https://([\w.-]+\.oraclecloud\.com)/hcmUI/CandidateExperience/[a-z]{2}/sites/([\w-]+)/job/(\d+)")


def api_description(url):
    """The job's description from the job site's public API, or '' if unknown."""
    from app.feeds import clean, get_json
    m = GREENHOUSE_URL.search(url) or GREENHOUSE_EMBED.search(url)
    if m:
        return clean(get_json(f"https://boards-api.greenhouse.io/v1/boards/{m.group(1)}/jobs/{m.group(2)}").get("content"))
    m = LEVER_URL.search(url)
    if m:
        data = get_json(f"https://api.lever.co/v0/postings/{m.group(1)}/{m.group(2)}")
        extra = " ".join(i.get("content", "") for i in data.get("lists", []))
        return clean(data.get("descriptionPlain", "") + " " + extra)
    m = WORKDAY_URL.search(url)
    if m:
        tenant, pod, site, path = m.groups()
        data = get_json(f"https://{tenant}.{pod}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{path}")
        return clean((data.get("jobPostingInfo") or {}).get("jobDescription"))
    m = ASHBY_URL.search(url)
    if m:
        board = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{m.group(1)}")
        job = next((j for j in board.get("jobs", []) if j.get("id") == m.group(2)), {})
        return clean(job.get("descriptionPlain") or job.get("descriptionHtml"))
    m = WORKABLE_URL.search(url)
    if m:
        data = get_json(f"https://apply.workable.com/api/v2/accounts/{m.group(1)}/jobs/{m.group(2)}")
        return clean(" ".join(data.get(k) or "" for k in ("description", "requirements", "benefits")))
    m = SMARTRECRUITERS_URL.search(url)
    if m:
        data = get_json(f"https://api.smartrecruiters.com/v1/companies/{m.group(1)}/postings/{m.group(2)}")
        sections = (data.get("jobAd") or {}).get("sections") or {}
        return clean(" ".join((v or {}).get("text", "") for v in sections.values()))
    m = BAMBOO_URL.search(url)
    if m:
        data = get_json(f"https://{m.group(1)}.bamboohr.com/careers/{m.group(2)}/detail")
        opening = (data.get("result") or {}).get("jobOpening") or {}
        return clean(opening.get("description"))
    m = RIPPLING_URL.search(url)
    if m:
        data = get_json(f"https://api.rippling.com/platform/api/ats/v1/board/{m.group(1)}/jobs/{m.group(2)}")
        desc = data.get("description") or {}
        return clean(" ".join(desc.values()) if isinstance(desc, dict) else desc)
    m = ORACLE_URL.search(url)
    if m:
        host, site, job_id = m.groups()
        data = get_json(f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
                        f"?expand=all&onlyData=true&finder=ById;Id=%22{job_id}%22,siteNumber={site}")
        item = (data.get("items") or [{}])[0]
        return clean(" ".join(item.get(k) or "" for k in (
            "ExternalDescriptionStr", "ExternalResponsibilitiesStr", "ExternalQualificationsStr")))
    return ""


def real_url(url):
    """Follow a short link (go.vansh.nyc/…) to the actual job page."""
    if not SHORT_LINK.match(url):
        return url
    try:
        return requests.head(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True).url
    except requests.RequestException:
        return url


def describe(job):
    """Fill in the description: the job site's API first, then the page itself."""
    from app.mail_alerts import add_description
    job["url"] = real_url(job["url"])
    try:
        text = api_description(job["url"])
    except Exception:
        text = ""                              # fall back to reading the page
    if len(text) > 200:
        job["description"] = text
        return job
    return add_description(job)


def dedupe(jobs):
    """The same role is often on several trackers: keep the first."""
    seen, out = set(), []
    for job in jobs:
        title = re.sub(r"\b(?:graduate|new grad|university grad(?:uate)?|early careers?|20\d\d)\b", " ",
                       clean_title(job["title"]).lower())
        key = (job["company"].strip().lower(), re.sub(r"[^a-z0-9]+", " ", title).strip())
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
