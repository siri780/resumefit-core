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
