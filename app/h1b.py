"""H-1B sponsorship history from the official USCIS H-1B Employer Data Hub.

When a posting doesn't mention visas, a company that got many H-1B approvals
recently is a much better bet than one that never sponsors. The watcher
downloads the USCIS file once a week and keeps per-company totals in its
database.
"""
import csv
import io
import re

import requests

DATA_URLS = [   # newest first; the first one that downloads is used
    "https://www.uscis.gov/sites/default/files/document/data/h1b_datahubexport-2025.csv",
    "https://www.uscis.gov/sites/default/files/document/data/h1b_datahubexport-2024.csv",
    "https://www.uscis.gov/sites/default/files/document/data/h1b_datahubexport-2023.csv",
]
BROWSER = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")}
MIN_APPROVALS = 10            # fewer than this isn't a real sponsorship track record
SUFFIXES = re.compile(
    r"\b(?:inc|incorporated|llc|l l c|corp|corporation|co|company|ltd|limited|lp|llp|"
    r"plc|pllc|pc|na|n a|holdings?|group|usa|us|america|technologies|technology)\b")

_cache = None                 # {normalized name: (approvals, year)}


def norm(name):
    """'Amazon.com Services, LLC' -> 'amazon com services'; 'Adobe Inc.' -> 'adobe'."""
    name = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower().replace("&", " and "))
    return re.sub(r"\s+", " ", SUFFIXES.sub(" ", name)).strip()


def _column(header, *words):
    for i, h in enumerate(header):
        low = h.lower()
        if all(w in low for w in words):
            return i
    return None


def totals_from_csv(text):
    """Per-company approvals from a USCIS export. Returns ({name: count}, year).

    Older files have 'Employer' + 'Initial Approval'/'Continuing Approval';
    newer ones say 'Employer (Petitioner) Name' + 'New Employment Approval' etc.
    Every column with 'approval' in its name is added up.
    """
    rows = csv.reader(io.StringIO(text.lstrip("﻿")))
    header = next(rows)
    who = _column(header, "employer") if _column(header, "employer", "name") is None \
        else _column(header, "employer", "name")
    year_col = _column(header, "year")
    approvals = [i for i, h in enumerate(header) if "approval" in h.lower()]
    if who is None or not approvals:
        raise ValueError("unexpected USCIS file format")
    totals, years = {}, set()
    for row in rows:
        if len(row) <= max([who] + approvals):
            continue
        name = norm(row[who])
        if not name:
            continue
        count = sum(int(re.sub(r"[^\d]", "", row[i]) or 0) for i in approvals)
        totals[name] = totals.get(name, 0) + count
        if year_col is not None and row[year_col].strip().isdigit():
            years.add(int(row[year_col]))
    return totals, (max(years) if years else None)


def setup(con):
    con.execute("CREATE TABLE IF NOT EXISTS h1b (name TEXT PRIMARY KEY, approvals INTEGER, year INTEGER)")


def refresh(con):
    """Download the newest USCIS file and save totals. Returns a list of errors."""
    setup(con)
    last = "no file"
    for url in DATA_URLS:
        try:
            response = requests.get(url, headers=BROWSER, timeout=120)
            response.raise_for_status()
            totals, year = totals_from_csv(response.content.decode("utf-8", "replace"))
        except Exception as error:
            code = getattr(getattr(error, "response", None), "status_code", "")
            last = f"{type(error).__name__} {code}".strip()
            continue
        year = year or int(re.search(r"(\d{4})\.csv", url).group(1))
        con.execute("DELETE FROM h1b")
        con.executemany("INSERT INTO h1b VALUES (?, ?, ?)",
                        [(n, c, year) for n, c in totals.items() if c >= MIN_APPROVALS])
        con.commit()
        global _cache
        _cache = None
        return []
    return [f"H-1B data: {last}"]


def _load():
    global _cache
    if _cache is None:
        try:
            from app.scan import connect
            con = connect()
            setup(con)
            _cache = {n: (c, y) for n, c, y in con.execute("SELECT name, approvals, year FROM h1b")}
        except Exception:
            _cache = {}
    return _cache


def history(company, table=None):
    """(approvals, year) for a company, or None. 'Amazon' also counts
    'Amazon Com Services' and 'Amazon Web Services'; very short names only
    match exactly, so 'Air' doesn't pick up 'Air Products'."""
    table = _load() if table is None else table
    name = norm(company)
    if not name:
        return None
    if name in table:
        return table[name]
    if len(name) < 4 and " " not in name:
        return None
    hits = [v for k, v in table.items() if k.startswith(name + " ")]
    if not hits:
        return None
    return sum(c for c, _ in hits), max(y for _, y in hits)
