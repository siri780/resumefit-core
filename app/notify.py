import html
import os

import requests


def send_telegram(text):
    """Send a message to your phone. Returns (ok, info)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False, "Telegram is not set up"
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": True},
        timeout=20,
    )
    return response.ok, response.json().get("description", "sent")


def format_alert(match):
    """Turn one ranked job into a short phone message."""
    e = html.escape
    missing = ", ".join(match["missing"][:5]) or "none"
    if match.get("ats") is None:
        missing = "scored once you paste the job into the web app"
        score_line = f"🎯 {match['tier']} · ATS: open the job to score it\n"
    else:
        score_line = (f"🎯 {match['tier']} · ATS {match['ats']}% · "
                      f"score {match['score']}\n")
    from app.posting_guard import inspect
    flags = inspect(match.get("description", ""), match.get("hidden_html", False))
    warning = (f"⚠️ Posting check: {e(', '.join(flags))}. Kept out of "
               "tailoring; skim the posting yourself.\n" if flags else "")
    via = (f"📧 From your {e(match.get('via') or match['company'])} "
           "job-alert email\n" if match.get("source") == "email" else "")
    return (
        f"🆕 <b>{e(match['company'])}</b> · {e(match['title'])}\n"
        f"📍 {e(match['location'] or 'see job')}\n"
        + via + score_line
        + f"📄 Use: {e(match.get('base', 'Data Scientist'))} resume"
        f"{' (title unclear, picked by match)' if match.get('base_how') == 'match' else ''}\n"
        f"🛂 {e(match['sponsorship'])}\n"
        f"❌ Missing: {e(missing)}\n"
        + warning
        + f"🔗 <a href=\"{e(match['url'])}\">Open job</a>"
    )


if __name__ == "__main__":
    print(send_telegram("✅ <b>ResumeFit</b> is connected. Job alerts will arrive here."))