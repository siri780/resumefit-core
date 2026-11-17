"""Weekly job-search scorecard in Telegram (Sunday evening).

Roles found, applications, referrals, replies, interviews and offers, for
the week and in total, plus where the good jobs came from. Until you have
20 strong applications it says so: that's too few to judge your resume.
"""
import html
from datetime import date, datetime, timedelta

from app.applications import TIMEZONE
from app.summary import setup

SEND_WEEKDAY = 6          # Sunday
SEND_HOUR = 18            # 6 PM New York time
WEEK_GOAL = 23 * 7        # ~700 applications a month
JUDGE_AFTER = 20          # applications needed before judging resume/targeting


def week_bounds(day):
    """Monday..Sunday of the week containing day (ISO dates)."""
    start = day - timedelta(days=day.weekday())
    return start.isoformat(), (start + timedelta(days=6)).isoformat()


def rejection_date(row):
    """'Rejection email 2026-11-14' in the notes -> '2026-11-14'."""
    notes = row.get("notes") or ""
    marker = "Rejection email "
    if marker in notes:
        return notes.split(marker, 1)[1][:10]
    return (row.get("date") or "")[:10] if row.get("status") == "Rejected" else ""


def tracker_stats(rows, start, end):
    in_week = lambda d: start <= d <= end
    applied = [r for r in rows if (r.get("date") or "")[:10]]
    week_apps = [r for r in applied if in_week(r["date"][:10])]
    status = lambda s: [r for r in rows if r.get("status") == s]
    referrals = [r for r in rows if "referr" in (r.get("notes") or "").lower()]
    return {
        "apps_week": len(week_apps),
        "apps_total": len(applied),
        "companies_week": len({r["company"] for r in week_apps}),
        "rejected_week": sum(in_week(rejection_date(r)) for r in status("Rejected")),
        "rejected_total": len(status("Rejected")),
        "interviews": len(status("Interview")),
        "offers": len(status("Offer")),
        "referrals_total": len(referrals),
        "referrals_week": sum(in_week((r.get("date") or "")[:10]) for r in referrals),
    }


def alert_stats(con, start, end):
    setup(con)
    total = con.execute("SELECT COUNT(*) FROM day_alerts WHERE day BETWEEN ? AND ?",
                        (start, end)).fetchone()[0]
    sources = con.execute(
        "SELECT name, SUM(value) FROM daily WHERE day BETWEEN ? AND ? "
        "AND name LIKE 'source:%' GROUP BY name ORDER BY SUM(value) DESC",
        (start, end)).fetchall()
    return total, [(n.split(":", 1)[1], v) for n, v in sources]


def scorecard_text(con, rows, day=None):
    day = day or datetime.now(TIMEZONE).date()
    start, end = week_bounds(day)
    t = tracker_stats(rows, start, end)
    alerts, sources = alert_stats(con, start, end)
    replies = t["rejected_total"] + t["interviews"] + t["offers"]
    rate = f"{replies / t['apps_total']:.0%}" if t["apps_total"] else "—"
    e = html.escape
    lines = [f"🗓 <b>Weekly scorecard</b> · {date.fromisoformat(start):%b %d} – "
             f"{date.fromisoformat(end):%b %d}",
             f"🔎 Matching roles found: {alerts}",
             f"📬 Applications: {t['apps_week']} this week "
             f"({t['companies_week']} companies) · goal {WEEK_GOAL} · {t['apps_total']} total",
             f"🤝 Referral requests: {t['referrals_week']} this week · {t['referrals_total']} total",
             f"❌ Rejections: {t['rejected_week']} this week · {t['rejected_total']} total",
             f"🎤 Interviews in progress: {t['interviews']}",
             f"🎉 Offers: {t['offers']}",
             f"📈 Reply rate (any answer): {rate}"]
    if sources:
        lines.append("📍 Where this week's matches came from: "
                     + ", ".join(f"{e(n)} {v}" for n, v in sources[:6]))
    if t["apps_total"] < JUDGE_AFTER:
        lines.append(f"\n⏳ {t['apps_total']}/{JUDGE_AFTER} strong applications: too early "
                     "to judge your resume or targeting. Keep going.")
    elif t["interviews"] + t["offers"] == 0:
        lines.append("\n🔧 20+ applications and no interviews yet: time to review your "
                     "resume and which roles you apply to. Referrals help most here.")
    lines.append("💡 Tip: write \"referral\" in a tracker row's notes when you ask "
                 "for one, so it's counted here.")
    return "\n".join(lines)


def maybe_send_scorecard(con, send, rows_loader=None):
    """Send once a week, Sunday after SEND_HOUR. Returns True if sent."""
    setup(con)
    now = datetime.now(TIMEZONE)
    if now.weekday() != SEND_WEEKDAY or now.hour < SEND_HOUR:
        return False
    key = now.date().isoformat()
    row = con.execute("SELECT value FROM state WHERE name = 'scorecard_day'").fetchone()
    if row and row[0] == key:
        return False
    rows = (rows_loader or load_rows)()
    if rows is None:
        return False
    send(scorecard_text(con, rows, now.date()))
    con.execute("INSERT OR REPLACE INTO state VALUES ('scorecard_day', ?)", (key,))
    con.commit()
    return True


def load_rows():
    """Your tracker rows, or None if the private tracker isn't connected."""
    import os
    if not os.getenv("APPS_REPO_TOKEN"):
        return None
    from app.applications import read_tracker
    from app.backup import refresh, restore
    try:
        restore()
        refresh(every_seconds=0)
        return read_tracker()
    except Exception as error:
        print(f"Scorecard: couldn't read tracker: {type(error).__name__}", flush=True)
        return None
