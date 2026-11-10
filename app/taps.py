"""Telegram "✨ Tailor my resume" button.

Every job alert carries a button. When you tap it, the next watcher run
tailors the matching base resume for that job and sends you both PDFs
(original and tailored) plus the list of edits, so you choose which to upload.
"""
import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

import requests

from app.applications import TIMEZONE

BUTTON_PREFIX = "t:"
PAUSE_PREFIX = "p:"
COVER_PREFIX = "c:"
KEEP_DAYS = 3
MAX_MESSAGE = 3900
RETRIES = 3


# ---------- Telegram ----------
def telegram(method, files=None, **params):
    """Call one Telegram Bot API method. Returns the JSON reply."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return {"ok": False, "description": "Telegram is not set up"}
    url = f"https://api.telegram.org/bot{token}/{method}"
    for attempt in range(RETRIES):
        if attempt:
            time.sleep(3 * attempt)          # brief pause, then try again
        for _, value in (files or {}).items():
            handle = value[1] if isinstance(value, tuple) else value
            if hasattr(handle, "seek"):
                handle.seek(0)               # resend the whole file
        try:
            if files:
                response = requests.post(url, data=params, files=files, timeout=60)
            else:
                response = requests.post(url, json=params, timeout=30)
            reply = response.json()
        except (requests.RequestException, ValueError) as error:
            reply = {"ok": False, "description": f"network error: {error}"}
            continue                         # connection dropped: retry
        break                                # Telegram answered (ok or not)
    if not reply.get("ok"):
        print(f"Telegram {method} failed: {reply.get('description')}",
              flush=True)
    return reply


def my_chat():
    return str(os.getenv("TELEGRAM_CHAT_ID", "")).strip()


def send_message(text, buttons=None):
    params = {"chat_id": my_chat(), "text": text[:MAX_MESSAGE],
              "parse_mode": "HTML", "disable_web_page_preview": True}
    if buttons:
        params["reply_markup"] = {"inline_keyboard": buttons}
    return telegram("sendMessage", **params)


def send_pdf(path, filename, caption):
    with open(path, "rb") as f:
        reply = telegram("sendDocument", files={"document": (filename, f)},
                         chat_id=my_chat(), caption=caption[:1000],
                         parse_mode="HTML")
    if not reply.get("ok"):
        raise RuntimeError(f"could not send {filename}: "
                           f"{reply.get('description')}")
    return reply


# ---------- Remembering alerted jobs ----------
def setup(con):
    con.execute("CREATE TABLE IF NOT EXISTS alerts "
                "(key TEXT PRIMARY KEY, job TEXT, created TEXT)")
    cutoff = (datetime.now(TIMEZONE) - timedelta(days=KEEP_DAYS)).isoformat()
    con.execute("DELETE FROM alerts WHERE created < ?", (cutoff,))
    con.commit()


def alert_key(job_id):
    return hashlib.sha1(job_id.encode("utf-8")).hexdigest()[:16]


def remember_alert(con, match):
    """Store what the button needs later. Returns the button rows."""
    setup(con)
    key = alert_key(match["id"])
    job = {k: match.get(k, "") for k in
           ("company", "title", "location", "url", "base", "description")}
    con.execute("INSERT OR REPLACE INTO alerts VALUES (?, ?, ?)",
                (key, json.dumps(job),
                 datetime.now(TIMEZONE).isoformat(timespec="minutes")))
    con.commit()
    rows = []
    if match.get("description"):       # both need the job description
        rows.append([{"text": "✨ Tailor my resume",
                      "callback_data": BUTTON_PREFIX + key},
                     {"text": "✉️ Cover letter",
                      "callback_data": COVER_PREFIX + key}])
    rows.append([{"text": "🔕 Pause company", "callback_data": PAUSE_PREFIX + key}])
    return rows


def find_alert(con, key):
    setup(con)
    row = con.execute("SELECT job FROM alerts WHERE key = ?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


# ---------- Reading taps ----------
def get_taps():
    """Unconfirmed button taps from you. Reading does NOT confirm them."""
    reply = telegram("getUpdates", timeout=0,
                     allowed_updates=["callback_query"])
    updates = reply.get("result", []) if reply.get("ok") else []
    taps, other = [], 0
    for u in updates:
        q = u.get("callback_query")
        if not q or not q.get("data", "").startswith(
                (BUTTON_PREFIX, PAUSE_PREFIX, COVER_PREFIX)):
            continue
        chat = str(q.get("message", {}).get("chat", {}).get("id", "")).strip()
        if chat == my_chat():
            taps.append(q)
        else:
            other += 1
    print(f"Telegram: {len(updates)} update(s), {len(taps)} tap(s) from you, "
          f"{other} tap(s) from another chat", flush=True)
    return updates, taps


def confirm(updates):
    """Tell Telegram these updates are handled so they never come back."""
    if updates:
        last = max(u["update_id"] for u in updates)
        telegram("getUpdates", offset=last + 1, limit=1, timeout=0)


# ---------- Tailoring ----------
def safe_name(text):
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_") or "Company"


def edits_message(job, before, after, applied, blocked, keywords=None):
    e = html.escape
    lines = [f"✨ <b>{e(job['company'])}</b> · {e(job['title'])}",
             f"📄 Base: {e(job['base'])} resume",
             f"📈 ATS {before['percent']}% → {after['percent']}%"]
    if keywords:
        lines.append(f"🔤 Keyword match {keywords[0]}% → {keywords[1]}%")
    lines.append("")
    if applied:
        lines.append(f"<b>{len(applied)} edit(s) in the tailored PDF:</b>")
        for n, s in enumerate(applied, 1):
            lines.append(f"\n{n}. <i>Before:</i> {e(readable(s['original']))}")
            lines.append(f"   <i>After:</i> {e(readable(s['new']))}")
    else:
        lines.append("No honest improvements found. Use the original.")
    if blocked:
        lines.append(f"\n🚫 {blocked} suggestion(s) blocked by the guard.")
    if after["missing"]:
        lines.append(f"\n❌ Still missing: {e(', '.join(after['missing'][:8]))}")
    lines.append(f"\n🔗 <a href=\"{e(job['url'])}\">Open job</a>")
    return "\n".join(lines)


def readable(text):
    return text.replace("\\%", "%").replace("\\&", "&")


def tailor_job(job):
    """Build both PDFs for one job and send them with the edit list."""
    from app.ats import find_skills, latex_to_text, load_skills, score
    from app.bases import DEFAULT, load_base
    from app.build_pdf import build_pdf
    from app.latex_io import apply_edits, get_bullets
    from app.pdf_check import check_pdf
    from app.tailor import tailor

    base = job.get("base") or DEFAULT
    job["base"] = base
    skills = load_skills()
    tex = load_base(base)
    text = latex_to_text(tex)
    before = score(text, job["description"], skills)

    # Send the original first, so you always get a usable PDF even if the
    # AI step fails (no credit, network error, ...).
    company = safe_name(job["company"])
    original_pdf = build_pdf(f"original_{company}", tex=tex)
    send_pdf(original_pdf, "Shirisha_Gajendra_Resume.pdf",
             f"📄 Original · {base} base · ATS {before['percent']}%")

    suggestions = tailor(get_bullets(tex), job["description"],
                         find_skills(text, skills), skills, before["missing"])
    applied = [s for s in suggestions if not s["problems"]]
    blocked = len(suggestions) - len(applied)

    from app.keywords import keyword_match
    kw_before = keyword_match(text, job["description"], job["company"])
    kw_after = kw_before
    after = before
    if applied:
        new_tex = apply_edits(tex, {s["id"]: s["new"] for s in applied})
        after = score(latex_to_text(new_tex), job["description"], skills)
        kw_after = keyword_match(latex_to_text(new_tex), job["description"],
                                 job["company"])
        tailored_pdf = build_pdf(f"tailored_{company}", tex=new_tex)
        problems = check_pdf(tailored_pdf, latex_to_text(new_tex))
        note = ("✅ 1 page · ATS-readable" if not problems
                else "⚠️ " + "; ".join(problems))
        send_pdf(tailored_pdf, f"Shirisha_Gajendra_Resume_{company}.pdf",
                 f"✨ Tailored for {html.escape(job['company'])} · "
                 f"ATS {after['percent']}% · {html.escape(note)}")

    reply = send_message(edits_message(
        job, before, after, applied, blocked,
        (kw_before["percent"], kw_after["percent"])))
    if not reply.get("ok"):
        send_message(f"✨ {html.escape(job['company'])}: tailored PDF sent "
                     f"(ATS {before['percent']}% → {after['percent']}%). "
                     "The edit list was too long to show.")


def handle_pause(con, q):
    """🔕 tap: stop alerts from that company for a while."""
    from app.cooldown import pause, pretty
    job = find_alert(con, q["data"][len(PAUSE_PREFIX):])
    if not job:
        telegram("answerCallbackQuery", callback_query_id=q["id"],
                 text="That alert is too old to pause from.")
        return
    until = pause(con, job["company"])
    telegram("answerCallbackQuery", callback_query_id=q["id"],
             text=f"🔕 Paused {job['company']} until {pretty(until)}")
    send_message(f"🔕 No more alerts from <b>{html.escape(job['company'])}</b> "
                 f"until {pretty(until)}.")
    print("Tap: paused a company", flush=True)


def handle_cover(con, q):
    """✉️ tap: write a cover letter and send it as a message to copy."""
    from app.bases import DEFAULT, load_base
    from app.cover_letter import write_letter
    job = find_alert(con, q["data"][len(COVER_PREFIX):])
    telegram("answerCallbackQuery", callback_query_id=q["id"],
             text="✉️ Writing it now. It arrives in a minute or two."
             if job else "That alert is too old.")
    if not job:
        return
    try:
        letter, removed = write_letter(job, load_base(job.get("base") or DEFAULT))
    except Exception as error:
        print(f"Tap: cover letter failed: {type(error).__name__}", flush=True)
        send_message(f"⚠️ Couldn't write the cover letter for "
                     f"{html.escape(job['company'])}: {html.escape(str(error))[:300]}")
        return
    note = (f"\n🚫 {len(removed)} sentence(s) removed by the guard "
            "(they added facts not on your resume)." if removed else "")
    send_message(f"✉️ <b>Cover letter · {html.escape(job['company'])}</b> · "
                 f"{html.escape(job['title'])}\nUses your {html.escape(job.get('base') or DEFAULT)} "
                 f"resume. Long-press the next message to copy it.{note}")
    send_message(html.escape(letter)[:MAX_MESSAGE])
    print("Tap: cover letter sent", flush=True)


def process_taps(con):
    """Handle every pending tap. Returns how many resumes were tailored."""
    updates, all_taps = get_taps()
    taps = []
    for q in all_taps:
        if q["data"].startswith(PAUSE_PREFIX):
            handle_pause(con, q)
        elif q["data"].startswith(COVER_PREFIX):
            handle_cover(con, q)
        else:
            taps.append(q)
    for q in taps:
        telegram("answerCallbackQuery", callback_query_id=q["id"],
                 text="⏳ Tailoring now. PDFs arrive in a few minutes.")
        job = find_alert(con, q["data"][len(BUTTON_PREFIX):])
        print(f"Tap: {'found' if job else 'NOT found'} in saved alerts",
              flush=True)
        if not job:
            send_message("⚠️ That alert is too old or its details were "
                         "lost. Paste the job into the ResumeFit web app.")
            continue
        try:
            tailor_job(job)
            print("Tap: tailored and sent", flush=True)
        except Exception as error:
            print(f"Tap: failed: {type(error).__name__}", flush=True)
            send_message(f"⚠️ Couldn't tailor {html.escape(job['company'])}: "
                         f"{html.escape(str(error))[:300]}")
    confirm(updates)
    return len(taps)


def has_taps():
    """True if a "Tailor" tap is waiting (pause taps don't need LaTeX)."""
    return any(q["data"].startswith(BUTTON_PREFIX) for q in get_taps()[1])


if __name__ == "__main__":
    # Used by the GitHub workflow: only install LaTeX when a tap is waiting.
    if "--check" in sys.argv:
        try:
            pending = has_taps()
        except Exception as error:
            print(f"Tap check failed: {error}")
            pending = False
        out = os.getenv("GITHUB_OUTPUT")
        if out:
            with open(out, "a", encoding="utf-8") as f:
                f.write(f"pending={'true' if pending else 'false'}\n")
        print(f"pending taps: {pending}")
