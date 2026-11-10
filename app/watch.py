import html
import sys
import time
from datetime import datetime, timedelta

from app.applications import TIMEZONE
from app.notify import format_alert, send_telegram
from app.scan import connect, scan, scan_email
from app.summary import bump, maybe_send_summary, record_alert
from app.app_emails import sync_applications, sync_message
from app.taps import process_taps, remember_alert, send_message
from app.cooldown import LIMIT, PAUSE_DAYS, WINDOW_DAYS, auto_pause, is_paused, pretty

INTERVAL_SECONDS = 60
SCAN_EVERY = timedelta(minutes=4, seconds=30)
WORKDAY_EVERY = timedelta(minutes=29)
MAX_ALERTS = 10


def due(con, name, every):
    """True (and remember now) if `every` has passed since `name` last ran."""
    con.execute("CREATE TABLE IF NOT EXISTS state "
                "(name TEXT PRIMARY KEY, value TEXT)")
    row = con.execute("SELECT value FROM state WHERE name = ?",
                      (name,)).fetchone()
    now = datetime.now(TIMEZONE)
    if row and now - datetime.fromisoformat(row[0]) < every:
        return False
    con.execute("INSERT OR REPLACE INTO state VALUES (?, ?)",
                (name, now.isoformat()))
    con.commit()
    return True


def run_once():
    """Handle button taps every run; scan for new jobs every ~5 minutes."""
    con = connect()
    try:
        tapped = process_taps(con)
    except Exception as error:
        tapped = 0
        print(f"Tap handling failed: {error}", flush=True)
    bump(con, "tailored", tapped)
    try:
        maybe_send_summary(con, send_message)
    except Exception as error:
        print(f"Summary failed: {error}", flush=True)
    now = datetime.now(TIMEZONE).strftime("%H:%M")
    if not due(con, "scan", SCAN_EVERY):
        print(f"[{now}] taps only · tailored={tapped}", flush=True)
        return
    include_workday = due(con, "workday", WORKDAY_EVERY)
    matches, errors, total = scan(include_workday)
    mail_matches, mail_errors = scan_email(con)
    errors += mail_errors
    matches = mail_matches + matches
    try:
        synced = sync_applications(con)
    except Exception as error:
        synced = None
        errors.append(f"Application emails: {type(error).__name__}")
    if synced and (synced[0] or synced[1] or synced[3]):
        added, rejected, added_today, interviews = synced
        send_message(sync_message(added, rejected, interviews))
        bump(con, "applied", added_today)
        bump(con, "rejected", len(rejected))
        from app.interview_prep import send_packs
        send_packs(con, interviews)
    newly_paused = pause_busy_companies(con)
    if newly_paused:
        send_message(pause_message(newly_paused))
    matches = [m for m in matches if not is_paused(con, m["company"])]
    if first_scan(con):
        for match in matches:
            record_alert(con, match)
        send_message(f"✅ ResumeFit is set up here. Saved {total} current jobs "
                     "quietly; you'll get alerts for new ones from now on.")
        print(f"[{now}] first run: saved {total} jobs without alerts", flush=True)
        return
    for match in matches[:MAX_ALERTS]:
        send_message(format_alert(match), remember_alert(con, match))
        record_alert(con, match)
    if len(matches) > MAX_ALERTS:
        send_telegram(f"…and {len(matches) - MAX_ALERTS} more new matches.")
    print(f"[{now}] checked {total} jobs · {len(matches)} matches · "
          f"{len(errors)} errors · workday={include_workday} · "
          f"tailored={tapped} · from email={len(mail_matches)}", flush=True)
    if errors:
        print("Errors: " + "; ".join(errors), flush=True)
    warn_if_gmail_disconnected(con, errors)


def first_scan(con):
    """True only on the very first scan with a fresh database (for example,
    after moving the watcher to a new repo), so old jobs don't flood you."""
    return due(con, "seeded", timedelta(days=36500))


def pause_busy_companies(con):
    """Pause companies you've already applied to LIMIT+ times recently."""
    import os
    if not os.getenv("APPS_REPO_TOKEN"):
        return []
    from app.applications import read_tracker
    from app.backup import refresh, restore
    try:
        restore()
        refresh(every_seconds=0)
        return auto_pause(con, read_tracker())
    except Exception as error:
        print(f"Cooldown check failed: {type(error).__name__}", flush=True)
        return []


def pause_message(newly):
    lines = [f"🔕 <b>Paused alerts</b> from companies with {LIMIT}+ applications "
             f"in the last {WINDOW_DAYS} days (for {PAUSE_DAYS} days):"]
    lines += [f"• {html.escape(name)} until {pretty(until)}" for name, until in newly]
    return "\n".join(lines)


GMAIL_WARNING = ("⚠️ <b>Gmail is disconnected</b>, so job-alert emails (Meta, "
                 "LinkedIn) and application tracking are paused.\n"
                 "Fix: in the resumefit codespace run "
                 "<code>python -m app.drive_login --gmail</code>, then update the "
                 "GMAIL_REFRESH_TOKEN secret on GitHub.")


def warn_if_gmail_disconnected(con, errors):
    """Tell you once a day if Gmail stopped working (expired sign-in)."""
    if any("RefreshError" in e for e in errors):
        if due(con, "gmail_warning", timedelta(hours=24)):
            send_message(GMAIL_WARNING)


if __name__ == "__main__":
    if "--once" in sys.argv:
        run_once()
    else:
        send_telegram("👀 ResumeFit watcher started. Checking every minute.")
        while True:
            try:
                run_once()
            except Exception as error:
                print(f"Run failed: {error}", flush=True)
            time.sleep(INTERVAL_SECONDS)
