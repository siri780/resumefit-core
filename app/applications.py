import csv
import re
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo

from app.ats import ROOT

APPS_DIR = ROOT / "applications"
TRACKER = APPS_DIR / "_Tracker.csv"
FIELDS = ["date", "company", "role", "ats_before", "ats_after",
          "status", "link", "folder", "notes"]
STATUSES = ["Applied", "Interview", "Rejected", "Offer", "Withdrawn"]
TIMEZONE = ZoneInfo("America/New_York")


def today_local():
    """Today's date in your time zone, e.g. '2026-10-20'."""
    return datetime.now(TIMEZONE).date().isoformat()


def read_tracker():
    """Return all saved applications as a list of dictionaries."""
    if not TRACKER.exists():
        return []
    with open(TRACKER, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_tracker(rows):
    """Overwrite the tracker with the given rows (used when editing status)."""
    APPS_DIR.mkdir(exist_ok=True)
    with open(TRACKER, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def already_applied(company, role):
    """True if this company + role is already in the tracker."""
    key = (company.strip().lower(), role.strip().lower())
    return any((r["company"].strip().lower(), r["role"].strip().lower()) == key
               for r in read_tracker())


def _norm(text):
    """'Two Sigma' and 'Twosigma' -> 'twosigma'; drops job numbers like (ID: 123)."""
    text = re.sub(r"\((?:id|job number|req)[^)]*\)|\b[A-Z]?-?\d{5,}\b", " ", text or "", flags=re.I)
    return re.sub(r"[^a-z0-9]", "", text.lower())


FILLER = {"2025", "2026", "2027", "2028", "start", "usa", "us", "remote", "hybrid",
          "onsite", "position", "role", "the", "a", "an", "of", "and", "for", "in", "at",
          "to", "with"}


def _words(title):
    """The words that make a job title distinct ('Senior', 'II', 'Grad' count)."""
    title = re.sub(r"\((?:id|job number|req)[^)]*\)|\b[A-Z]{0,2}-?\d{5,}\b", " ",
                   title or "", flags=re.I)
    return frozenset(re.findall(r"[a-z0-9]+", title.lower())) - FILLER


def applied_keys(rows=None):
    """(company, title words) for every job already in the tracker."""
    rows = read_tracker() if rows is None else rows
    return {(_norm(r["company"]), _words(r["role"])) for r in rows
            if _norm(r["company"]) and len(_words(r["role"])) >= 2}


def applied_before(job, keys):
    """True if the tracker already has this company and the same job title.

    Small differences are fine ("Quantitative Researcher: Machine Learning" vs
    "Quantitative Researcher - Machine Learning", "(ID: 123)", "2027 Start"),
    but a different level is a different job ("Data Scientist II" vs "III").
    """
    company, words = _norm(job["company"]), _words(job["title"])
    if not company or not words:
        return False
    return any((c == company or (len(c) >= 4 and (c in company or company in c)))
               and role == words for c, role in keys)


def safe_part(text):
    """Turn text into a safe folder-name part."""
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_") or "Unknown"


def save_application(company, role, jd, tex, pdf_path, before, after, link=""):
    """Save PDF, .tex, job description and ATS report; add a tracker row."""
    APPS_DIR.mkdir(exist_ok=True)
    today = today_local()
    folder = APPS_DIR / f"{today}_{safe_part(company)}_{safe_part(role)}"
    folder.mkdir(exist_ok=True)

    shutil.copy(pdf_path, folder / pdf_path.name)
    (folder / "resume.tex").write_text(tex, encoding="utf-8")
    (folder / "job_description.txt").write_text(jd, encoding="utf-8")
    report = (f"ATS before: {before['percent']}%\n"
              f"ATS after: {after['percent']}%\n"
              f"Matched: {', '.join(after['matched'])}\n"
              f"Missing: {', '.join(after['missing'])}\n")
    (folder / "ats_report.txt").write_text(report, encoding="utf-8")

    new_file = not TRACKER.exists()
    with open(TRACKER, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow({
            "date": today, "company": company, "role": role,
            "ats_before": before["percent"], "ats_after": after["percent"],
            "status": "Applied", "link": link,
            "folder": folder.name, "notes": "",
        })
    return folder
