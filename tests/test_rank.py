from app.rank import assess, is_relevant, tier, years_required


def job(title, location="New York, NY", description=""):
    return {"title": title, "location": location, "description": description}


def test_relevant_roles_and_skips():
    assert is_relevant(job("Data Scientist, New Grad"))
    assert not is_relevant(job("Data Science Intern"))
    assert not is_relevant(job("Account Executive"))
    assert not is_relevant(job("Data Scientist", location="London, UK"))
    assert is_relevant(job("Data Scientist", location="Remote - United States"))


def test_years_required():
    assert years_required("3+ years of experience") == 3
    assert years_required("2-4 years in analytics") == 2
    assert years_required("no experience needed") is None


def test_tiers():
    assert tier(job("Data Scientist I")) == "Target"
    assert tier(job("Senior Data Scientist")) == "Reach"
    assert tier(job("Staff ML Engineer")) == "Long shot"
    assert tier(job("Data Scientist", description="4+ years")) == "Stretch"


def test_citizenship_is_blocked():
    result = assess(job("Data Scientist I", description="Must be a US citizen."), 95)
    assert result["blocked"] and not result["show"]


def test_reach_needs_high_match():
    senior = job("Senior Data Scientist")
    assert not assess(senior, 70)["show"]
    assert assess(senior, 80)["show"]

def test_foreign_locations_are_skipped():
    assert not is_relevant(job("Data Scientist", location="Warsaw; Poznan"))
    assert not is_relevant(job("Software Engineer, New Grad", location="Taipei"))
    assert not is_relevant(job("Data Scientist", location="Pune, IN"))
    assert is_relevant(job("Data Scientist", location="US, MA, Westford"))
    assert is_relevant(job("Data Scientist", location="Bengaluru, India; Seattle, WA"))
    assert is_relevant(job("Data Scientist", location="2 Locations"))


def test_knockouts():
    from app.rank import knockouts
    assert knockouts(job("Analyst", description="Sponsorship is not available for this role"))
    assert knockouts(job("Analyst", description="Associate of Society of Actuaries (ASA) designation"))
    assert not knockouts(job("Analyst", description="CFA preferred"))
    assert knockouts(job("Scientist", description="A Ph.D. in CS or equivalent experience."))
    assert not knockouts(job("Scientist", description="MS or PhD in statistics"))
    assert knockouts(job("Staff Data Scientist"))
    assert knockouts(job("Data Scientist", description="10+ years of experience"))


def test_knocked_out_jobs_are_hidden():
    result = assess(job("Data Scientist I", description="We do not sponsor visas."), 95)
    assert result["blocked"] and not result["show"]


def test_more_foreign_locations_are_skipped():
    from app.rank import outside_us
    assert outside_us("Kuwait City, Kuwait")
    assert outside_us("Doha, Qatar")
    assert outside_us("Lima, Peru")
    assert not outside_us("Lima, Ohio")              # a U.S. state wins
    assert not outside_us("New York, NY")
    assert not outside_us("Remote - United States")


def test_more_no_sponsorship_wordings():
    from app.rank import no_sponsorship
    for t in ["we do not sponsor visas for this role",
              "we are unable to support visa applications",
              "no h-1b transfers", "candidates not eligible to receive sponsorship",
              "we won't sponsor", "we cannot currently provide visa sponsorship",
              "this position is not eligible for immigration sponsorship.",
              "sponsorship is not offered for this role"]:
        assert no_sponsorship(t), t
    for t in ["we offer visa sponsorship", "h-1b sponsorship available",
              "you will sponsor experiments across teams"]:
        assert not no_sponsorship(t), t


def test_us_person_is_word_bounded():
    from app.rank import knockouts
    base = {"title": "Data Scientist", "location": "New York, NY"}
    blocked = knockouts({**base, "description": "Must be a U.S. person under ITAR."})
    assert "Requires U.S. citizenship or security clearance" in blocked
    ok = knockouts({**base, "description": "A focus person for our analytics team."})
    assert "Requires U.S. citizenship or security clearance" not in ok


def test_frontend_and_mobile_roles_are_knocked_out():
    from app.rank import frontend_role
    for t in ["Software Engineer, Profile & Community, Web", "Frontend Engineer",
              "Senior Front-End Developer", "iOS Engineer", "Android Developer",
              "Software Engineer - Mobile", "UI Engineer"]:
        assert frontend_role(t), t
    for t in ["Data Scientist, Web Analytics", "Machine Learning Engineer",
              "Software Engineer, Backend", "Data Engineer", "Full Stack Engineer",
              "Web Analyst"]:
        assert not frontend_role(t), t


def test_remote_job_with_foreign_country_in_description_is_knocked_out():
    from app.rank import hidden_foreign_location, knockouts
    base = {"title": "Data Scientist III", "company": "ClassPass"}
    uk = {**base, "location": "Remote",
          "description": "ClassPass | Pricing & Inventory | Full-time | United Kingdom | Remote. At Playlist..."}
    us = {**base, "location": "Remote",
          "description": "Full-time | United States | Remote. We partner with teams in London and Toronto."}
    later = {**base, "location": "Remote",
             "description": "Build models in Python. " * 30 + "Our offices are in London."}
    named = {**base, "location": "New York, NY", "description": "United Kingdom office collaboration"}
    assert hidden_foreign_location(uk) == "United Kingdom"
    assert any("Outside the U.S." in r for r in knockouts(uk))
    assert hidden_foreign_location(us) == ""          # U.S. mentioned at the top
    assert hidden_foreign_location(later) == ""       # far down the page doesn't count
    assert hidden_foreign_location(named) == ""       # real U.S. location given
