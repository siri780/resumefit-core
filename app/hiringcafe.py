"""Jobs from HiringCafe (hiring.cafe), which collects postings straight from
company career sites.

HiringCafe has no official API: this uses the same search endpoint its
website uses. If they block it or change the format, this source simply
returns an error line and everything else keeps working.
"""
import requests

from app.feeds import SEARCHES, TIMEOUT, make_job

URL = "https://hiring.cafe/api/search-jobs"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://hiring.cafe",
    "Referer": "https://hiring.cafe/",
}
PAST_DAYS = 2
PAGE_SIZE = 200
US = {"formatted_address": "United States", "types": ["country"],
      "geometry": {"location": {"lat": "39.8283", "lon": "-98.5795"}},
      "id": "user_country",
      "address_components": [{"long_name": "United States", "short_name": "US",
                              "types": ["country"]}],
      "options": {"flexible_regions": ["anywhere_in_continent", "anywhere_in_world"]}}


def search_state(query):
    return {"searchQuery": query, "locations": [US],
            "workplaceTypes": ["Remote", "Hybrid", "Onsite"],
            "commitmentTypes": ["Full Time"],
            "seniorityLevel": ["No Prior Experience Required", "Entry Level", "Mid Level"],
            "dateFetchedPastNDays": PAST_DAYS, "sortBy": "default",
            "defaultToUserLocation": False}


def _first(*values):
    return next((v for v in values if isinstance(v, str) and v.strip()), "")


def to_job(hit):
    """One HiringCafe result -> a ResumeFit job (None if it's unusable)."""
    hit = hit.get("_source", hit)
    info = hit.get("job_information") or {}
    data = hit.get("v5_processed_job_data") or hit.get("processed_job_data") or {}
    company_data = hit.get("enriched_company_data") or hit.get("v5_processed_company_data") or {}
    title = _first(info.get("title"), data.get("core_job_title"), hit.get("title"))
    company = _first(data.get("company_name"), company_data.get("name"),
                     hit.get("company_name"), hit.get("source"))
    url = _first(hit.get("apply_url"), hit.get("url"))
    if not (title and company and url):
        return None
    location = _first(data.get("formatted_workplace_location"), hit.get("location"))
    posted = _first(data.get("estimated_publish_date"), hit.get("date_posted"))
    job = make_job(company, f"hc-{hit.get('id') or url}", title, location, url, posted,
                   _first(info.get("description"), hit.get("description")))
    return {**job, "source": "tracker", "via": "HiringCafe"}


def hits_from(data):
    """HiringCafe has returned results under a few different keys."""
    if isinstance(data, list):
        return data
    for key in ("results", "jobs", "data", "items"):
        if isinstance(data.get(key), list):
            return data[key]
    hits = data.get("hits")
    if isinstance(hits, dict):
        return hits.get("hits", [])
    return hits if isinstance(hits, list) else []


def fetch_hiringcafe_jobs():
    """Returns (jobs, errors)."""
    jobs, errors, seen = [], [], set()
    session = requests.Session()
    session.headers.update(HEADERS)
    for query in SEARCHES:
        try:
            response = session.post(URL, timeout=TIMEOUT * 2, json={
                "size": PAGE_SIZE, "page": 0, "searchState": search_state(query)})
            response.raise_for_status()
            hits = hits_from(response.json())
        except Exception as error:
            code = getattr(getattr(error, "response", None), "status_code", "")
            errors.append(f"HiringCafe: {type(error).__name__} {code}".strip())
            break                       # blocked once = blocked for all queries
        for hit in hits:
            job = to_job(hit)
            if job and job["id"] not in seen:
                seen.add(job["id"])
                jobs.append(job)
    return jobs, errors


if __name__ == "__main__":
    found, problems = fetch_hiringcafe_jobs()
    print(f"HiringCafe: {len(found)} jobs · errors: {problems or 'none'}")
    for j in found[:10]:
        print(f"  {j['company']} – {j['title']} ({j['location']}) "
              f"{len(j['description'])} chars")
      
