"""Log your applications automatically from confirmation and rejection emails.

Almost every company emails "Thank you for applying" after you apply, and
many email again if they reject you. This reads those emails (Gmail,
read-only), adds new applications to your tracker, and marks rejections.
"""
import html
import re
from datetime import datetime

from app.applications import TIMEZONE

# Gmail search for application emails (confirmations and decisions).
QUERY_PHRASES = [
    '"thank you for applying"', '"thanks for applying"',
    '"received your application"', '"application has been received"',
    '"officially applied"', '"your application for"',
    '"confirm that your application"', '"moving forward"',
    '"other candidates"', '"not been selected"', '"regret to inform"',
    '"interview"', '"assessment"', '"next steps"', '"phone screen"',
]
EXCLUDE = ("-from:linkedin.com -from:indeed.com -from:glassdoor.com "
           "-from:ziprecruiter.com -from:handshake.com")

REJECTED = [
    "not be moving forward", "won't be moving forward", "won’t be moving forward",
    "will not be moving forward", "not moving forward with your",
    "decided to move forward with other", "move forward with other candidates",
    "decided to pursue other", "not been selected", "were not selected",
    "regret to inform", "unable to offer you", "position has been filled",
    "decided not to proceed", "not to proceed with your",
    "not pursuing you", "other candidates who more closely",
]
INTERVIEW = [
    "schedule an interview", "schedule your interview",
    "invite you to interview", "invite you to an interview",
    "invitation to interview", "interview invitation",
    "phone screen", "technical screen", "recruiter screen", "next round",
    "share your availability", "provide your availability", "your availability for",
    "online assessment", "coding assessment", "technical assessment",
    "complete the assessment", "invite you to complete", "coding challenge",
    "hackerrank", "codesignal", "karat", "hirevue",
    "would like to move forward with your application",
    "excited to move forward with your application",
]
APPLIED = [
    "thank you for applying", "thanks for applying", "received your application",
    "application has been received", "application was received",
    "officially applied", "confirm that your application",
    "your application for", "we have received your application",
    "your application was sent to",
]

# Workday sends from <tenant>@myworkday.com; a few tenants need nicer names.
TENANT_NAMES = {"fmr": "Fidelity Investments", "cvshealth": "CVS Health",
                "nvidia": "NVIDIA", "jpmc": "JPMorgan Chase",
                "bankofamerica": "Bank of America", "wellsfargo": "Wells Fargo"}
GENERIC_SENDERS = {"no-reply", "noreply", "donotreply", "do-not-reply",
                   "notifications", "careers", "jobs", "recruiting", "talent"}
ATS_DOMAINS = ("greenhouse-mail.io", "greenhouse.io", "lever.co", "ashbyhq.com",
               "myworkday.com", "icims.com", "smartrecruiters.com",
               "successfactors.com", "taleo.net", "jobvite.com")

REQ_ID = re.compile(r"^(?:[A-Z]{1,4}[-_]?\d{4,}|\d{5,})(?:[-_]\d+)?\s+")
ROLE_PATTERNS = [
    re.compile(r"(?:applying|applied|application|apply)\s+(?:for|to):?\s+"
               r"(?:our\s+|the\s+)?(?:position\s+of\s+)?:?\s*(?P<role>.+?)"
               r"(?=\s+(?:role|position|job|opening|posting)\b|,\s*we\b|\s+and\s+for\b"
               r"|\.\s|\.$|\s+at\s+[A-Z]|\s+has\s+been\b|\s+with\s+[A-Z]"
               r"|\s*\((?:Open|Closed)\)|\s+We\b|$)", re.I),
]
SUBJECT_PATTERNS = [
    re.compile(r"your application for (?P<role>.+?) at (?P<company>.+)$", re.I),
    re.compile(r"application for the (?P<role>.+?) position", re.I),
]
VAGUE_ROLE = re.compile(r"^(?:a|an|this|that|the|our|your|any|one|other)\b|^(?:us|jobs?|roles?)$",
                        re.I)
UPDATE_SUBJECT = re.compile(
    r"update on your (?P<company>[\w&.' -]+?) application:\s*(?P<role>.+)$", re.I)
COMPANY_IN_TEXT = re.compile(
    r"(?:interest in|joining|opening at|role at|position at|team at|apply(?:ing)? to)\s+"
    r"(?:the\s+)?(?P<company>[A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,3})")


def clean_role(role):
    role = html.unescape(role).strip(" :-,.")
    role = REQ_ID.sub("", role)
    role = re.sub(r"\s*\((?:Open|Closed)\)\s*$", "", role, flags=re.I)
    return re.sub(r"\s+", " ", role).strip(" :-,.")[:120]


def is_decision(text, phrase):
    """True if the rejection phrase is a statement, not "if we ... other candidates"."""
    start = text.find(phrase)
    while start != -1:
        before = text[max(0, start - 80):start]
        if not re.search(r"\b(?:if|should|in case|whether|may|might)\b", before):
            return True
        start = text.find(phrase, start + 1)
    return False


def classify(subject, body):
    """'rejected', 'interview', 'applied' or None."""
    text = f"{subject}\n{body}".lower().replace("’", "'")
    if any(is_decision(text, p.replace("’", "'")) for p in REJECTED):
        return "rejected"
    if any(p in text for p in INTERVIEW):
        return "interview"
    if any(p in text for p in APPLIED):
        return "applied"
    return None


def company_from_sender(sender):
    m = re.search(r"([\w.+-]+)@([\w.-]+)", sender or "")
    if not m:
        return ""
    local, domain = m.group(1).lower(), m.group(2).lower()
    if domain.endswith("myworkday.com") and local not in GENERIC_SENDERS:
        return TENANT_NAMES.get(local, local.replace("-", " ").title())
    if any(domain.endswith(d) for d in ATS_DOMAINS):
        return ""                               # shared ATS sender: look in text
    parts = domain.split(".")
    name = parts[-2] if len(parts) >= 2 else parts[0]
    return TENANT_NAMES.get(name, name.title())


def extract(subject, body, sender):
    """Return (company, role) from one application email ('' if unknown)."""
    found = linkedin_applied(subject, body)
    if found:
        return found
    subject = html.unescape(subject or "")
    body = html.unescape(re.sub(r"\s+", " ", body or ""))
    company, role = "", ""
    for pattern in SUBJECT_PATTERNS:
        m = pattern.search(subject)
        if m:
            role = clean_role(m.group("role"))
            company = (m.groupdict().get("company") or "").strip(" .!")
            break
    if not role:
        for pattern in ROLE_PATTERNS:
            for m in pattern.finditer(body):     # first specific job title
                candidate = clean_role(m.group("role"))
                if len(candidate) >= 4 and not VAGUE_ROLE.search(candidate):
                    role = candidate
                    break
            if role:
                break
    if not role:
        m = UPDATE_SUBJECT.search(subject)
        if m:
            role, company = clean_role(m.group("role")), m.group("company").strip()
    company = company_from_sender(sender) or company
    for text in (subject, body):
        if company:
            break
        m = COMPANY_IN_TEXT.search(text)
        if m:
            company = m.group("company").strip(" .!")
    return company, role


def same_job(row, company, role):
    """Loose match: same company, and roles equal or one contains the other."""
    if row["company"].strip().lower() != company.strip().lower():
        return False
    a, b = row["role"].strip().lower(), role.strip().lower()
    return not b or a == b or a in b or b in a


def apply_emails(rows, emails, interviews=None):
    """Update tracker rows from parsed emails. Returns (rows, added, rejected).
    Interview invites are added to `interviews` as (company, role) pairs."""
    added, rejected = [], []
    interviews = [] if interviews is None else interviews
    for e in sorted(emails, key=lambda e: e["date"]):
        kind = classify(e["subject"], e["body"])
        if not kind:
            continue
        company, role = extract(e["subject"], e["body"], e["sender"])
        if not company:
            continue
        matches = [r for r in rows if same_job(r, company, role)]
        if kind == "applied" and role and not matches:
            rows.append({"date": e["date"], "company": company, "role": role,
                         "ats_before": "", "ats_after": "", "status": "Applied",
                         "link": "", "folder": "", "notes": "Logged from email"})
            added.append(f"{company} – {role}")
        elif kind == "interview":
            if not matches and not role:   # newsletters and tips mention interviews too
                continue
            open_rows = [r for r in matches if r["status"] == "Applied"]
            for r in open_rows[:1]:
                r["status"] = "Interview"
                r["notes"] = (r["notes"] + "; " if r["notes"] else "") + \
                    f"Interview email {e['date']}"
            if not matches:
                rows.append({"date": e["date"], "company": company,
                             "role": role or "Interview", "ats_before": "",
                             "ats_after": "", "status": "Interview", "link": "",
                             "folder": "", "notes": "Interview email"})
            if open_rows or not matches:
                interviews.append((company, open_rows[0]["role"] if open_rows else role))
        elif kind == "rejected":
            open_rows = [r for r in matches if r["status"] in ("Applied", "Interview")]
            if role and not matches:
                rows.append({"date": e["date"], "company": company, "role": role,
                             "ats_before": "", "ats_after": "", "status": "Rejected",
                             "link": "", "folder": "", "notes": "Rejection email"})
                rejected.append(f"{company} – {role}")
            elif len(open_rows) == 1 or (role and open_rows):
                for r in open_rows[:1]:
                    r["status"] = "Rejected"
                    r["notes"] = (r["notes"] + "; " if r["notes"] else "") + \
                        f"Rejection email {e['date']}"
                    rejected.append(f"{company} – {r['role']}")
    return rows, added, rejected


# ---------- Gmail ----------
LINKEDIN_APPLIED = 'from:jobs-noreply@linkedin.com "your application was sent"'
LINKEDIN_SENT = re.compile(r"your application was sent to (?P<company>.+?)\s*$", re.I)


def gmail_query(days):
    return (f"newer_than:{days}d ((({' OR '.join(QUERY_PHRASES)}) {EXCLUDE}) "
            f"OR ({LINKEDIN_APPLIED}))")


def linkedin_applied(subject, body):
    """(company, role) from a LinkedIn Easy Apply confirmation, or None."""
    m = LINKEDIN_SENT.search(html.unescape(subject or ""))
    if not m:
        return None
    company = m.group("company").strip(" .!")
    text = re.sub(r"\s+", " ", html.unescape(body or ""))
    role = ""
    r = re.search(r"application was sent to " + re.escape(company) +
                  r"\s+(?P<role>.{3,120}?)\s+" + re.escape(company) + r"\s*[·•]",
                  text, re.I)
    if r:
        role = clean_role(r.group("role"))
    return company, role or "LinkedIn Easy Apply"


def plain_text(payload):
    from app.mail_alerts import html_part
    body = html_part(payload)
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    return html.unescape(re.sub(r"<[^>]+>", " ", body))


def fetch_application_emails(service, days, skip_ids=()):
    """Application emails from the last `days` days, newest first."""
    listing = service.users().messages().list(
        userId="me", q=gmail_query(days), maxResults=100).execute()
    emails = []
    for ref in listing.get("messages", []):
        if ref["id"] in skip_ids:
            continue
        msg = service.users().messages().get(userId="me", id=ref["id"],
                                             format="full").execute()
        headers = {h["name"].lower(): h["value"]
                   for h in msg["payload"].get("headers", [])}
        when = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, TIMEZONE)
        emails.append({"id": ref["id"], "date": when.date().isoformat(),
                       "subject": headers.get("subject", ""),
                       "sender": headers.get("from", ""),
                       "body": plain_text(msg["payload"])[:5000]})
    return emails


# ---------- Keeping the tracker in sync ----------
def sync_applications(con, service=None):
    """Read new application emails and update the tracker in the private repo.

    Returns (added, rejected, added_today, interviews), or None when Gmail or the private repo
    isn't connected. Emails are only marked as done after a successful backup,
    so nothing is lost if a push fails.
    """
    import os

    from app.applications import read_tracker, write_tracker
    from app.backup import backup, refresh, restore

    if not (os.getenv("GMAIL_REFRESH_TOKEN") and os.getenv("APPS_REPO_TOKEN")):
        return None
    con.execute("CREATE TABLE IF NOT EXISTS app_emails (id TEXT PRIMARY KEY)")
    seen = {row[0] for row in con.execute("SELECT id FROM app_emails")}
    if service is None:
        from app.mail_alerts import gmail_service
        service = gmail_service()
    days = 3 if seen else 60          # first run: catch up on recent weeks
    emails = fetch_application_emails(service, days, seen)
    if not emails:
        return [], [], 0, []

    restore()
    refresh(every_seconds=0)
    interviews = []
    rows, added, rejected = apply_emails(read_tracker(), emails, interviews)
    if added or rejected or interviews:
        write_tracker(rows)
        ok, message = backup(f"Log {len(added)} application(s), "
                             f"{len(rejected)} rejection(s), "
                             f"{len(interviews)} interview(s) from email")
        if not ok:
            print(message, flush=True)
            return [], [], 0, []
    con.executemany("INSERT OR IGNORE INTO app_emails VALUES (?)",
                    [(e["id"],) for e in emails])
    con.commit()
    today = datetime.now(TIMEZONE).date().isoformat()
    added_today = sum(1 for r in rows if r["date"] == today
                      and f"{r['company']} – {r['role']}" in added)
    return added, rejected, added_today, interviews


def sync_message(added, rejected, interviews=()):
    """Short Telegram note about what was logged."""
    e = html.escape
    lines = []
    if interviews:
        lines.append(f"🎉 <b>{len(interviews)} interview invite(s)!</b> Marked in your tracker:")
        lines += [f"• {e(c)} – {e(r or 'role not found')}" for c, r in interviews[:15]]
        lines.append("A prep pack for each is on its way.\n")
    if added:
        lines.append(f"📬 <b>Logged {len(added)} application(s)</b> from your email:")
        lines += [f"• {e(a)}" for a in added[:15]]
    if rejected:
        lines.append(f"\n❌ <b>{len(rejected)} rejection(s)</b> marked in your tracker:")
        lines += [f"• {e(r)}" for r in rejected[:15]]
        lines.append("Keep going: rejections are part of the numbers game.")
    return "\n".join(lines)
