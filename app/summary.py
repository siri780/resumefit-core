"""A short evening summary in Telegram: what ResumeFit did today."""
import html
from datetime import datetime

from app.applications import TIMEZONE

SUMMARY_HOUR = 20          # 8 PM New York time
DAILY_GOAL = 23            # ~700 applications a month


def setup(con):
    con.execute("CREATE TABLE IF NOT EXISTS daily "
                "(day TEXT, name TEXT, value INTEGER, PRIMARY KEY (day, name))")
    con.execute("CREATE TABLE IF NOT EXISTS day_alerts "
                "(day TEXT, score INTEGER, company TEXT, title TEXT, url TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS state "
                "(name TEXT PRIMARY KEY, value TEXT)")


def today():
    return datetime.now(TIMEZONE).date().isoformat()


def bump(con, name, amount=1):
    """Add to one of today's counters (alerts, tailored, ...)."""
    if not amount:
        return
    setup(con)
    con.execute("INSERT INTO daily VALUES (?, ?, ?) ON CONFLICT(day, name) "
                "DO UPDATE SET value = value + excluded.value",
                (today(), name, amount))
    con.commit()


def record_alert(con, match):
    """Remember an alert so the summary can list the day's best jobs."""
    setup(con)
    con.execute("INSERT INTO day_alerts VALUES (?, ?, ?, ?, ?)",
                (today(), match.get("score") or 0, match["company"],
                 match["title"], match["url"]))
    con.commit()
    bump(con, "alerts")


def tracker_counts(day):
    """(applied today, applied in the last 7 days) from your tracker.

    Counts every application in the tracker: ones saved in the web app and
    ones logged from confirmation emails. Returns None if the private
    tracker repo isn't connected."""
    import os
    from datetime import date, timedelta
    if not os.getenv("APPS_REPO_TOKEN"):
        return None
    from app.applications import read_tracker
    from app.backup import refresh, restore
    try:
        restore()
        refresh(every_seconds=0)
        rows = read_tracker()
    except Exception as error:
        print(f"Summary: couldn't read tracker: {type(error).__name__}", flush=True)
        return None
    week_start = (date.fromisoformat(day) - timedelta(days=6)).isoformat()
    dates = [(r.get("date") or "")[:10] for r in rows]
    return sum(d == day for d in dates), sum(week_start <= d <= day for d in dates)


def summary_text(con, day=None, counts_from_tracker=True):
    setup(con)
    day = day or today()
    counts = dict(con.execute("SELECT name, value FROM daily WHERE day = ?",
                              (day,)).fetchall())
    best = con.execute("SELECT company, title, url FROM day_alerts WHERE day = ? "
                       "ORDER BY score DESC LIMIT 5", (day,)).fetchall()
    e = html.escape
    lines = ["📊 <b>ResumeFit · today</b>",
             f"🆕 Job alerts sent: {counts.get('alerts', 0)}",
             f"✨ Resumes tailored: {counts.get('tailored', 0)}",
             applied_line(counts.get('applied', 0),
                          tracker_counts(day) if counts_from_tracker else None),
             f"❌ Rejections: {counts.get('rejected', 0)}"]
    from app.cooldown import paused_now, pretty
    paused = paused_now(con)
    if paused:
        lines.append("🔕 Paused: " + ", ".join(f"{e(n)} (until {pretty(u)})"
                                              for n, u in paused[:8]))
    if best:
        lines.append("\n<b>Today's best matches</b> (apply if you haven't):")
        for company, title, url in best:
            lines.append(f"• <a href=\"{e(url)}\">{e(company)} · {e(title)}</a>")
    else:
        lines.append("\nNo new matching jobs today.")
    return "\n".join(lines)


def applied_line(counter, tracked):
    """Applications today: the tracker is the source of truth when available."""
    if tracked is None:
        return (f"📬 Applications logged: {counter} / {DAILY_GOAL} daily goal "
                "(≈700 a month)")
    today_n, week_n = tracked
    return (f"📬 Applications today: {max(today_n, counter)} / {DAILY_GOAL} goal · "
            f"this week: {week_n} / {DAILY_GOAL * 7}")


def maybe_send_summary(con, send):
    """Send the summary once a day, after SUMMARY_HOUR. Returns True if sent."""
    setup(con)
    now = datetime.now(TIMEZONE)
    if now.hour < SUMMARY_HOUR:
        return False
    row = con.execute("SELECT value FROM state WHERE name = 'summary_day'"
                      ).fetchone()
    if row and row[0] == today():
        return False
    send(summary_text(con))
    con.execute("INSERT OR REPLACE INTO state VALUES ('summary_day', ?)",
                (today(),))
    con.commit()
    return True
