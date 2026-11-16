import pytest

from app.app_emails import apply_emails, classify, extract

# Real subject / sender / opening lines from application emails.
EMAILS = [
    ("Thank you for your interest in joining Reddit", "no-reply@us.greenhouse-mail.io",
     "Hi Shirisha, We want to thank you for your interest in Reddit. We have received your application for our Software Engineer, Ad Signals role and are working as fast as we can to review it.",
     "Reddit", "Software Engineer, Ad Signals"),
    ("Your Humana application: Next Steps", "humana@myworkday.com",
     "Hi Shirisha, Thank you for applying for R-422978 Associate Actuarial - Analytics/Forecasting, we're excited to have received your application.",
     "Humana", "Associate Actuarial - Analytics/Forecasting"),
    ("Thank you for your application", "Roche-Workday-DoNotReply@roche.com",
     "Hi Shirisha , Thank you for applying to AI Data Scientist - Applied AI and for your interest in joining us on our journey.",
     "Roche", "AI Data Scientist - Applied AI"),
    ("Great News! We've Received Your Application for the Software Engineering LMTS / PMTS - Software Factory (REMOTE) Position",
     "salesforce@myworkday.com",
     "Hi Shirisha, You have officially applied for the Software Engineering LMTS / PMTS - Software Factory (REMOTE) opening at Salesforce.",
     "Salesforce", "Software Engineering LMTS / PMTS - Software Factory (REMOTE)"),
    ("Your application with CVS Health has been received!", "cvshealth@myworkday.com",
     "Dear Shirisha, Thank you for your interest in joining CVS Health! We've successfully received your application for: R1082147 Data Scientist - Retail Demand Sensing (Open) To check your application",
     "CVS Health", "Data Scientist - Retail Demand Sensing"),
    ("Thank you for your interest in NVIDIA", "nvidia@myworkday.com",
     "Dear Shirisha Gajendra - We want to confirm that your application for the JR2018371 Software Engineer, Workflow Systems role has been received.",
     "NVIDIA", "Software Engineer, Workflow Systems"),
    ("Thank You For Applying", "fmr@myworkday.com",
     "Dear Shirisha, Thank you for applying to the position of 2131396 Analyst, Fraud Data Analytics and Insights. We have received your application.",
     "Fidelity Investments", "Analyst, Fraud Data Analytics and Insights"),
    ("Your application for Master's University Grad Data Scientist (USA) at Pinterest", "no-reply@us.greenhouse-mail.io",
     "Hi Shirisha, Thank you for your interest in joining the Pinterest team! We appreciate the time you took to apply.",
     "Pinterest", "Master's University Grad Data Scientist (USA)"),
    ("Thanks for Applying to Adobe", "adobe@myworkday.com",
     "Dear Shirisha Gajendra , We wanted to let you know that we received your application for the R172085 2027 University Graduate - Machine Learning Engineer role.",
     "Adobe", "2027 University Graduate - Machine Learning Engineer"),
]


@pytest.mark.parametrize("subject,sender,body,company,role", EMAILS)
def test_extracts_company_and_role(subject, sender, body, company, role):
    assert classify(subject, body) == "applied"
    assert extract(subject, body, sender) == (company, role)


def test_rejections_are_detected_and_update_the_tracker():
    pinterest = ("Your application for Master's University Grad Data Scientist (USA) at Pinterest",
                 "no-reply@pinterest.com",
                 "Thank you so much for your interest in Pinterest. Our recruiting team carefully reviewed your background and experience and, unfortunately, we won’t be moving forward with your application at this time.")
    humana = ("An Update on Your Humana Application: R-422978 Associate Actuarial - Analytics/Forecasting",
              "humana@myworkday.com",
              "Thank you for taking the time to apply for R-422978 Associate Actuarial - Analytics/Forecasting. We will not be moving forward with your candidacy for this position.")
    assert classify(pinterest[0], pinterest[2]) == "rejected"
    assert classify(humana[0], humana[2]) == "rejected"
    assert extract(humana[0], humana[2], humana[1]) == ("Humana", "Associate Actuarial - Analytics/Forecasting")

    emails = [{"date": "2026-10-18", "subject": s, "sender": f, "body": b}
              for s, f, b, *_ in EMAILS if "Pinterest" in s or "Humana" in s]
    emails += [{"date": "2026-10-22", "subject": pinterest[0], "sender": pinterest[1], "body": pinterest[2]},
               {"date": "2026-10-26", "subject": humana[0], "sender": humana[1], "body": humana[2]}]
    rows, added, rejected = apply_emails([], emails)
    assert len(rows) == 2 and len(added) == 2 and len(rejected) == 2
    assert {r["status"] for r in rows} == {"Rejected"}


def test_duplicates_and_unrelated_emails_are_ignored():
    survey = {"date": "2026-10-24", "subject": "Please provide feedback on your application process with Humana",
              "sender": "humanacareers@humana.com",
              "body": "Thank you for applying to the Associate Actuarial - Analytics/Forecasting job. Please complete our survey."}
    first = {"date": "2026-10-24", "subject": EMAILS[1][0], "sender": EMAILS[1][1], "body": EMAILS[1][2]}
    news = {"date": "2026-10-24", "subject": "Weekly newsletter", "sender": "news@example.com", "body": "Big news this week"}
    rows, added, _ = apply_emails([], [first, survey, news])
    assert len(rows) == 1 and len(added) == 1


def test_vague_phrases_are_not_taken_as_job_titles():
    body = ("We appreciate the time you took to apply for a role with us. "
            "We have received your application for the Data Scientist, Growth position.")
    assert extract("Thanks!", body, "no-reply@us.greenhouse-mail.io")[1] == "Data Scientist, Growth"


def test_sync_updates_tracker_once(monkeypatch, tmp_path):
    import app.app_emails as ae
    import app.applications as apps
    import app.backup as bk
    from app.scan import connect

    monkeypatch.setenv("GMAIL_REFRESH_TOKEN", "x")
    monkeypatch.setenv("APPS_REPO_TOKEN", "y")
    monkeypatch.setattr(apps, "TRACKER", tmp_path / "_Tracker.csv")
    monkeypatch.setattr(apps, "APPS_DIR", tmp_path)
    monkeypatch.setattr(bk, "restore", lambda: None)
    monkeypatch.setattr(bk, "refresh", lambda **k: None)
    pushed = []
    monkeypatch.setattr(bk, "backup", lambda msg: pushed.append(msg) or (True, "ok"))
    batch = [{"id": "m1", "date": "2026-10-24", "subject": EMAILS[5][0],
              "sender": EMAILS[5][1], "body": EMAILS[5][2]}]
    monkeypatch.setattr(ae, "fetch_application_emails",
                        lambda service, days, seen: [e for e in batch if e["id"] not in seen])
    con = connect(tmp_path / "t.db")
    added, rejected, _, _ = ae.sync_applications(con, service=object())
    assert added == ["NVIDIA – Software Engineer, Workflow Systems"] and pushed
    assert apps.read_tracker()[0]["status"] == "Applied"
    assert ae.sync_applications(con, service=object()) == ([], [], 0, [])   # not repeated
    assert "Logged 1 application" in ae.sync_message(added, rejected)


def test_conditional_wording_is_not_a_rejection():
    body = ("Thank you for applying for the Data Scientist role. If we decide to move forward "
            "with other candidates, we will let you know by email.")
    assert classify("Thank you for applying", body) == "applied"


def test_linkedin_easy_apply_confirmation():
    from app.app_emails import classify, extract
    subject = "Shirisha, your application was sent to Kargo"
    body = ("Your application was sent to Kargo\n\nMachine Learning Engineer\n"
            "Kargo · New York, NY (On-site)\nApplied on October 27, 2026")
    assert classify(subject, body) == "applied"
    assert extract(subject, body, "LinkedIn <jobs-noreply@linkedin.com>") == \
        ("Kargo", "Machine Learning Engineer")
    # Unknown layout: still logged, with a placeholder role.
    assert extract(subject, "Thanks!", "jobs-noreply@linkedin.com") == \
        ("Kargo", "LinkedIn Easy Apply")


def test_gmail_query_includes_linkedin_confirmations():
    from app.app_emails import gmail_query
    q = gmail_query(3)
    assert "-from:linkedin.com" in q and "jobs-noreply@linkedin.com" in q


# Real confirmation emails that used to be misread (Nov 2026).
def test_confirmation_promising_an_interview_is_not_an_invite():
    body = ("We've received your application for the Data Analyst role. Once we've "
            "had a chance to review your background, we will reach out to schedule "
            "an interview as soon as possible if your experience looks like a good fit.")
    assert classify("Thank you for applying to Deepgram!", body) == "applied"


def test_if_you_dont_hear_back_is_not_a_rejection():
    body = ("We have received your interest application for the Data Scientist "
            "position. If you do not hear from us within 30 calendar days, it is "
            "likely that we have decided to move forward with other candidates.")
    assert classify("Thank You for Your Application to AIR", body) == "applied"


def test_real_invites_and_rejections_still_detected():
    assert classify("Interview invitation", "We'd love to invite you to interview. "
                    "Please share your availability.") == "interview"
    assert classify("Your application", "We have decided not to move forward "
                    "with your application.") == "rejected"
    assert classify("Update", "Unfortunately, we won’t be moving forward with "
                    "your application at this time.") == "rejected"


def test_roles_read_correctly_from_tricky_emails():
    assert extract("Update on Salesforce’s Software Engineering MTS",
                   "If you applied for multiple positions, your other applications "
                   "may still be in consideration.",
                   "salesforce@myworkday.com") == ("Salesforce", "Software Engineering MTS")
    assert extract("Thank you for applying to DoorDash",
                   "Thank you for applying to DoorDash's Senior Data Scientist, "
                   "Brand Analytics position! We've received your application.",
                   "no-reply@doordash.com") == ("DoorDash", "Senior Data Scientist, Brand Analytics")
    assert extract("Thank you for applying to Robinhood",
                   "Thanks for applying to Robinhood! Your application has been received.",
                   "no-reply@robinhood.com")[1] == ""
    assert extract("Your application for Master's University Grad Data Scientist (USA) at Pinterest",
                   "", "no-reply@pinterest.com")[1] == "Master's University Grad Data Scientist (USA)"


def test_if_shortlisted_assessment_is_not_an_invite():
    body = ("Thank you for applying for the role of R1526366 - Senior Software Engineer "
            "(React), IQVIA Digital . We will review your application, and if you are "
            "shortlisted, you will proceed to the next step, which may include an "
            "initial screening and/or an online assessment.")
    assert classify("Thank you for Applying!", body) == "applied"
    assert extract("Thank you for Applying!", body, "iqvia@myworkday.com")[1] == \
        "Senior Software Engineer (React)"


def test_more_real_rejection_wordings():
    assert classify("Amazon application: Status update",
                    "After careful consideration and review of your application, we have "
                    "decided to progress with other candidates for this role.") == "rejected"
    assert classify("Update from Reddit",
                    "After carefully considering your background and qualifications we have "
                    "decided not to move forward in the process at this time.") == "rejected"
    assert classify("Your Application",
                    "we regret to inform you that we have decided to move ahead with other "
                    "candidates who we feel are a better match.") == "rejected"


def test_role_found_after_a_bad_first_match():
    assert extract("Thank you for applying to Databricks!",
                   "Thanks for applying to Databricks! Your application for the Software "
                   "Engineer - New Grad (2027 Start) role has been received.",
                   "no-reply@us.greenhouse-mail.io") == \
        ("Databricks", "Software Engineer - New Grad (2027 Start)")
    assert extract("Thank you for Applying to Amazon!",
                   "Hi Shirisha, Thanks for applying to Amazon! We've received your "
                   "application for the Data Scientist III (ID: 10591731) position.",
                   "noreply@mail.amazon.jobs") == ("Amazon", "Data Scientist III")
    assert extract("Thank you for your interest in Two Sigma",
                   "received your application for the following position: Quantitative "
                   "Researcher: Machine Learning What happens now?",
                   "noreply@twosigma.com") == ("Two Sigma", "Quantitative Researcher: Machine Learning")
    assert extract("Thank you for applying to OpenAI",
                   "Thank you for applying to OpenAI. Your application has been received",
                   "no-reply@openai.com") == ("OpenAI", "")
