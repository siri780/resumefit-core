"""Pause alerts from companies you can't apply to again for a while.

Big companies cap applications (for example a few per month). Once you have
applied several times to one company, more alerts from it only waste your
time, so ResumeFit pauses that company:

* automatically, when your tracker shows LIMIT or more applications to it in
  the last WINDOW_DAYS days, and
* manually, when you tap "🔕 Pause company" under an alert.
"""
import re
from datetime import date, datetime, timedelta

from app.applications import TIMEZONE

LIMIT = 3            # applications to one company ...
WINDOW_DAYS = 30     # ... within this many days
PAUSE_DAYS = 60      # pause its alerts for this long

SUFFIXES = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|llc|ltd|"
                      r"plc|group|holdings|technologies|technology|labs)\b")


def setup(con):
    con.execute("CREATE TABLE IF NOT EXISTS paused "
                "(company TEXT PRIMARY KEY, name TEXT, until TEXT, reason TEXT)")


def norm(company):
    """Compare companies loosely: 'Capital One, Inc.' == 'capital one'."""
    text = re.sub(r"[^a-z0-9 ]", " ", (company or "").lower())
    return re.sub(r"\s+", " ", SUFFIXES.sub(" ", text)).strip()


def today():
    return datetime.now(TIMEZONE).date()


def pause(con, company, days=PAUSE_DAYS, reason="manual"):
    """Pause a company until `days` from today. Returns the end date."""
    setup(con)
    until = (today() + timedelta(days=days)).isoformat()
    row = con.execute("SELECT until FROM paused WHERE company = ?",
                      (norm(company),)).fetchone()
    if row and row[0] >= until:            # already paused for longer
        return row[0]
    con.execute("INSERT OR REPLACE INTO paused VALUES (?, ?, ?, ?)",
                (norm(company), company.strip(), until, reason))
    con.commit()
    return until


def is_paused(con, company):
    """The pause end date if the company is paused today, else None."""
    setup(con)
    row = con.execute("SELECT until FROM paused WHERE company = ?",
                      (norm(company),)).fetchone()
    return row[0] if row and row[0] >= today().isoformat() else None


def paused_now(con):
    """[(name, until)] for every company paused today, soonest first."""
    setup(con)
    return con.execute("SELECT name, until FROM paused WHERE until >= ? "
                       "ORDER BY until", (today().isoformat(),)).fetchall()


def auto_pause(con, rows):
    """Pause companies with LIMIT+ tracker rows in the last WINDOW_DAYS.

    Returns [(name, until)] for companies newly paused this time."""
    since = (today() - timedelta(days=WINDOW_DAYS)).isoformat()
    counts, names = {}, {}
    for r in rows:
        if (r.get("date") or "") >= since and r.get("company"):
            key = norm(r["company"])
            counts[key] = counts.get(key, 0) + 1
            names.setdefault(key, r["company"].strip())
    newly = []
    for key, n in counts.items():
        if n >= LIMIT and not is_paused(con, names[key]):
            newly.append((names[key], pause(con, names[key], reason=f"{n} applications")))
    return newly


def pretty(until):
    return date.fromisoformat(until).strftime("%b %d")
