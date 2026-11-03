import csv
import html
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from app.ats import ROOT

COMPANIES_FILE = ROOT / "data" / "companies.csv"
HEADERS = {"User-Agent": "ResumeFit personal job alerts"}
TIMEOUT = 20
SEARCHES = ["data scientist", "machine learning", "data analyst",
            "software engineer"]


def get_json(url):
    """Download a URL and return its JSON; raise an error on 404 etc."""
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def clean(text):
    """Turn HTML job descriptions into plain text."""
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def make_job(company, job_id, title, location, url, posted, description):
    """One job in the same shape, whichever system it came from."""
    return {"id": f"{company}:{job_id}", "company": company, "title": title,
            "location": location or "", "url": url, "posted": posted or "",
            "description": clean(description)}


def greenhouse(company, slug):
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    return [make_job(company, j["id"], j["title"],
                     (j.get("location") or {}).get("name"), j["absolute_url"],
                     j.get("updated_at"), j.get("content"))
            for j in data["jobs"]]


def lever(company, slug):
    data = get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    jobs = []
    for j in data:
        posted = datetime.fromtimestamp(j["createdAt"] / 1000, timezone.utc)
        extra = " ".join(item.get("content", "") for item in j.get("lists", []))
        jobs.append(make_job(company, j["id"], j["text"],
                             (j.get("categories") or {}).get("location"),
                             j["hostedUrl"], posted.isoformat(),
                             j.get("descriptionPlain", "") + " " + extra))
    return jobs


def ashby(company, slug):
    data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    return [make_job(company, j["id"], j["title"], j.get("location"),
                     j["jobUrl"], j.get("publishedAt"),
                     j.get("descriptionPlain") or j.get("descriptionHtml"))
            for j in data["jobs"]]


def workday_parts(careers_url):
    """Split a Workday careers URL into host, tenant and site."""
    url = urlparse(careers_url)
    host = url.netloc
    tenant = host.split(".")[0]
    site = url.path.strip("/").split("/")[-1]
    return host, tenant, site


def workday(company, careers_url):
    host, tenant, site = workday_parts(careers_url)
    api = f"https://{host}/wday/cxs/{tenant}/{site}"
    jobs, seen = [], set()
    for query in SEARCHES:
        response = requests.post(
            f"{api}/jobs", headers=HEADERS, timeout=TIMEOUT,
            json={"appliedFacets": {}, "limit": 20, "offset": 0,
                  "searchText": query})
        response.raise_for_status()
        for j in response.json().get("jobPostings") or []:
            path = j.get("externalPath")
            if not path or not j.get("title") or path in seen:
                continue  # some boards include half-empty entries
            seen.add(path)
            job = make_job(company, path, j["title"], j.get("locationsText"),
                           f"https://{host}/{site}{path}", j.get("postedOn"), "")
            job["detail_api"] = f"{api}{path}"
            jobs.append(job)
    return jobs


def job_description(job):
    """Fetch a Workday job's description only when it's actually needed."""
    if job.get("detail_kind") == "apple":       # has a summary; fetch the full text once
        summary = job["description"]
        try:
            response = requests.get(job["detail_api"], headers=BROWSER, timeout=TIMEOUT)
            texts = _texts(apple_page_data(response.text), APPLE_TEXT_KEYS) if response.ok else []
        except (requests.RequestException, ValueError):
            texts = []
        full = clean(" ".join(dict.fromkeys(texts)))      # dedupe, keep order
        job["description"] = full if len(full) > len(summary) else summary
        job["detail_kind"] = "apple-done"
        return job["description"]
    if job["description"] or not job.get("detail_api"):
        return job["description"]
    if job.get("detail_kind") == "microsoft":
        try:
            response = requests.get(job["detail_api"], headers=BROWSER,
                                    timeout=TIMEOUT)
            data = response.json().get("data") or {} if response.ok else {}
        except (requests.RequestException, ValueError):
            data = {}
        job["description"] = clean(data.get("jobDescription"))
        return job["description"]
    info = get_json(job["detail_api"]).get("jobPostingInfo", {})
    job["description"] = clean(info.get("jobDescription"))
    places = [info.get("location")] + list(info.get("additionalLocations") or [])
    country = (info.get("country") or {}).get("descriptor")
    places = [p for p in places + [country] if p]
    if places:
        job["location"] = "; ".join(places)
    return job["description"]


def amazon(company, slug=""):
    """Amazon's public job search (U.S. only, newest first)."""
    jobs, seen = [], set()
    for query in SEARCHES:
        response = requests.get(
            "https://www.amazon.jobs/en/search.json", headers=HEADERS,
            timeout=TIMEOUT,
            params={"base_query": query, "country": "USA",
                    "result_limit": 100, "sort": "recent"})
        response.raise_for_status()
        for j in response.json().get("jobs", []):
            if j["id_icims"] in seen:
                continue
            seen.add(j["id_icims"])
            description = " ".join(filter(None, [
                j.get("description"),
                "Basic qualifications:", j.get("basic_qualifications"),
                "Preferred qualifications:", j.get("preferred_qualifications")]))
            jobs.append(make_job(
                company, j["id_icims"], j["title"],
                j.get("normalized_location") or j.get("location"),
                "https://www.amazon.jobs" + j["job_path"],
                j.get("posted_date"), description))
    return jobs


BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
           "Accept-Language": "en-US,en;q=0.9"}
GOOGLE_RESULTS = "https://www.google.com/about/careers/applications/jobs/results/"
GOOGLE_DATA = re.compile(r"AF_initDataCallback\(\{key: 'ds:1', hash: '\d+', "
                         r"data:(.*?), sideChannel: \{\}\}\);</script>", re.S)


def _part(entry, i):
    """Text from a Google job field shaped like [null, "<html>"]."""
    try:
        value = entry[i]
        return value[1] if isinstance(value, list) and len(value) > 1 else ""
    except (IndexError, TypeError):
        return ""


def google_jobs_from_page(page, company="Google"):
    """Jobs embedded in one Google Careers results page."""
    m = GOOGLE_DATA.search(page)
    if not m:
        raise ValueError("Google Careers page layout changed")
    jobs = []
    for e in json.loads(m.group(1))[0] or []:
        places = []
        for place in (e[9] if len(e) > 9 and isinstance(e[9], list) else []):
            if isinstance(place, list) and place and isinstance(place[0], str):
                places.append(place[0])
        posted = ""
        if len(e) > 12 and isinstance(e[12], list) and e[12]:
            posted = datetime.fromtimestamp(e[12][0], timezone.utc).isoformat()
        description = " ".join(filter(None, [
            _part(e, 3), "Qualifications:", _part(e, 4), _part(e, 10)]))
        jobs.append(make_job(company, e[0], e[1], "; ".join(places),
                             f"{GOOGLE_RESULTS}{e[0]}", posted, description))
    return jobs


def google(company, slug=""):
    """Google Careers search (U.S., newest first), read from the public page."""
    jobs, seen = [], set()
    for query in SEARCHES:
        for page in (1, 2):
            response = requests.get(
                GOOGLE_RESULTS, headers=BROWSER, timeout=TIMEOUT,
                params={"q": query, "location": "United States",
                        "sort_by": "date", "page": page})
            response.raise_for_status()
            for job in google_jobs_from_page(response.text, company):
                if job["id"] not in seen:
                    seen.add(job["id"])
                    jobs.append(job)
    return jobs


MICROSOFT_API = "https://apply.careers.microsoft.com/api/pcsx/"


def _microsoft_get(url, params):
    """One polite request to Microsoft Careers; waits and retries once if
    Microsoft says "too many requests". Returns the JSON, or None."""
    for wait in (0, 20):
        time.sleep(wait or 1.5)
        response = requests.get(url, params=params, headers=BROWSER,
                                timeout=TIMEOUT)
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()
    print("Microsoft Careers: too many requests, trying again next run",
          flush=True)
    return None


def microsoft(company, slug=""):
    """Microsoft Careers search (U.S.). Descriptions are fetched only when needed."""
    jobs, seen = [], set()
    for query in SEARCHES:
        for start in (0, 10):
            data = _microsoft_get(MICROSOFT_API + "search", {
                "domain": "microsoft.com", "query": query,
                "location": "United States", "start": start})
            if data is None:
                return jobs                # rate-limited: keep what we have
            positions = (data.get("data") or {}).get("positions") or []
            for p in positions:
                if p["id"] in seen:
                    continue
                seen.add(p["id"])
                posted = (datetime.fromtimestamp(p["postedTs"], timezone.utc).isoformat()
                          if p.get("postedTs") else "")
                job = make_job(company, p["id"], p["name"],
                               "; ".join(p.get("locations") or []),
                               f"https://apply.careers.microsoft.com/careers/job/{p['id']}",
                               posted, "")
                job["detail_api"] = (f"{MICROSOFT_API}position_details?position_id="
                                     f"{p['id']}&domain=microsoft.com&hl=en")
                job["detail_kind"] = "microsoft"
                jobs.append(job)
            if len(positions) < 10:
                break
    return jobs


APPLE_SEARCH = "https://jobs.apple.com/en-us/search"
APPLE_DATA = re.compile(r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\(("(?:[^"\\]|\\.)*")\)', re.S)
APPLE_TEXT_KEYS = ("jobSummary", "description", "responsibilities", "minimumQualifications",
                   "preferredQualifications", "keyQualifications", "educationAndExperience")


def apple_page_data(page):
    """The JSON that Apple's careers pages embed for their own app."""
    m = APPLE_DATA.search(page)
    if not m:
        raise ValueError("Apple Careers page layout changed")
    return json.loads(json.loads(m.group(1)))


def apple_jobs_from_page(page, company="Apple"):
    """Jobs listed on one Apple Careers search page."""
    data = apple_page_data(page)
    results = ((data.get("loaderData") or {}).get("search") or {}).get("searchResults") or []
    jobs = []
    for j in results:
        if not j.get("postExternal", True):
            continue
        places = [", ".join(x for x in (p.get("name"), p.get("countryName")) if x)
                  for p in j.get("locations") or []]
        job = make_job(company, j["id"], j.get("postingTitle", ""), "; ".join(places),
                       f"https://jobs.apple.com/en-us/details/{j['id']}/"
                       f"{j.get('transformedPostingTitle', '')}",
                       j.get("postDateInGMT"), j.get("jobSummary", ""))
        job["detail_api"] = job["url"]          # full text fetched only when needed
        job["detail_kind"] = "apple"
        jobs.append(job)
    return jobs


def apple(company, slug=""):
    """Apple Careers search (U.S., newest first), read from the public pages."""
    jobs, seen = [], set()
    for query in SEARCHES:
        for page in (1, 2):
            response = requests.get(APPLE_SEARCH, headers=BROWSER, timeout=TIMEOUT,
                                    params={"search": query, "sort": "newest",
                                            "location": "united-states-USA", "page": page})
            response.raise_for_status()
            found = apple_jobs_from_page(response.text, company)
            for job in found:
                if job["id"] not in seen:
                    seen.add(job["id"])
                    jobs.append(job)
            if len(found) < 20:
                break
    return jobs


def _texts(obj, keys):
    """Every string stored under one of `keys`, anywhere in nested JSON."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and isinstance(v, str):
                out.append(v)
            else:
                out += _texts(v, keys)
    elif isinstance(obj, list):
        for v in obj:
            out += _texts(v, keys)
    return out


READERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby,
           "workday": workday, "amazon": amazon, "google": google,
           "microsoft": microsoft, "apple": apple}
SLOW_SOURCES = {"workday", "amazon", "google", "microsoft", "apple"}  # every ~30 minutes


def load_companies():
    with open(COMPANIES_FILE, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fetch_all(include_workday=True):
    """Read every company's jobs. Returns (jobs, errors)."""
    jobs, errors = [], []
    for c in load_companies():
        if c["source"] in SLOW_SOURCES and not include_workday:
            continue
        try:
            jobs += READERS[c["source"]](c["company"], c["slug"])
        except Exception as error:
            errors.append(f"{c['company']}: {type(error).__name__}")
    return jobs, errors


if __name__ == "__main__":
    for c in load_companies():
        try:
            count = len(READERS[c["source"]](c["company"], c["slug"]))
            print(f"✅ {c['company']}: {count} jobs")
        except Exception as error:
            print(f"❌ {c['company']} ({c['source']}/{c['slug']}): "
                  f"{type(error).__name__}")