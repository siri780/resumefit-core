import re

ROLE_WORDS = ["data scientist", "data science", "machine learning", "ml engineer",
              "data analyst", "analytics", "software engineer", "ai engineer",
              "applied scientist", "research scientist", "quantitative", "quant ",
              "data engineer", "statistician", "decision scientist"]
SKIP_TITLE = ["intern", "internship", "co-op"]
BLOCKERS = ["u.s. citizen", "us citizen", "citizenship is required",
            "security clearance", "secret clearance", "green card holder"]
NO_SPONSOR = ["not sponsor", "no sponsorship", "unable to sponsor",
              "without sponsorship", "not provide sponsorship",
              "not offer sponsorship", "sponsorship is not available",
              "sponsorship not available", "not available for sponsorship",
              "cannot sponsor", "does not sponsor", "will not sponsor",
              "no visa sponsorship", "not eligible for sponsorship",
              "sponsorship will not be", "unable to provide sponsorship"]
YES_SPONSOR = ["visa sponsorship", "will sponsor", "h-1b", "h1b"]
FLEXIBLE = ["or equivalent", "master's", "masters", "ms in", "m.s."]
TARGET_WORDS = ["new grad", "new college grad", "university grad", "early career",
                "entry level", "entry-level", "2027", "junior", "associate"]
REACH_WORDS = ["senior", "sr.", "sr ", "lead"]
LONGSHOT_WORDS = ["staff", "principal", "director", "head of", "manager",
                  "distinguished"]
FOREIGN = ["india", "london", "united kingdom", "england", "scotland", "canada",
           "toronto", "vancouver", "montreal", "ontario", "singapore", "dublin",
           "ireland", "germany", "berlin", "munich", "frankfurt", "amsterdam",
           "netherlands", "sydney", "melbourne", "australia", "tokyo", "japan",
           "hong kong", "paris", "france", "bengaluru", "bangalore", "hyderabad",
           "pune", "mumbai", "chennai", "gurgaon", "gurugram", "noida", "delhi",
           "poland", "warsaw", "poznan", "krakow", "wroclaw", "mexico", "brazil",
           "sao paulo", "israel", "tel aviv", "zurich", "basel", "switzerland",
           "spain", "madrid", "barcelona", "lisbon", "portugal", "italy",
           "milan", "china", "shanghai", "beijing", "shenzhen", "taipei",
           "taiwan", "seoul", "korea", "philippines", "manila", "vietnam",
           "argentina", "buenos aires", "colombia", "bogota", "chile",
           "costa rica", "romania", "bucharest", "czech", "prague", "hungary",
           "budapest", "sweden", "stockholm", "denmark", "copenhagen",
           "norway", "oslo", "finland", "helsinki", "belgium", "brussels",
           "austria", "vienna", "uae", "dubai", "saudi", "egypt", "nigeria",
           "kenya", "south africa", "new zealand", "malaysia", "kuala lumpur",
           "indonesia", "jakarta", "thailand", "bangkok", "emea", "apac",
           "latam", "latin america", "europe", "united arab emirates", "luxembourg", "estonia",
           "lithuania", "ukraine", "turkey", "istanbul", "greece", "athens"]
US_STATES = ["alabama", "alaska", "arizona", "arkansas", "california",
             "colorado", "connecticut", "delaware", "florida", "georgia",
             "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas",
             "kentucky", "louisiana", "maine", "maryland", "massachusetts",
             "michigan", "minnesota", "mississippi", "missouri", "montana",
             "nebraska", "nevada", "new hampshire", "new jersey", "new mexico",
             "new york", "north carolina", "north dakota", "ohio", "oklahoma",
             "oregon", "pennsylvania", "rhode island", "south carolina",
             "south dakota", "tennessee", "texas", "utah", "vermont",
             "virginia", "washington", "west virginia", "wisconsin", "wyoming",
             "district of columbia"]
US_CITIES = ["san francisco", "seattle", "boston", "chicago", "austin",
             "los angeles", "atlanta", "denver", "dallas", "houston",
             "philadelphia", "pittsburgh", "san jose", "santa clara",
             "mountain view", "palo alto", "menlo park", "sunnyvale",
             "redmond", "bellevue", "cambridge, ma", "nyc", "bay area",
             "silicon valley", "raleigh", "durham", "salt lake", "phoenix",
             "miami", "minneapolis", "detroit", "columbus", "charlotte",
             "nashville", "portland", "san diego", "irvine", "brooklyn",
             "manhattan", "jersey city", "hoboken", "westford", "cupertino"]
US_ABBR = re.compile(r"(?:,|\b)\s*(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|"
                     r"KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|"
                     r"OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\b")
US_WORDS = re.compile(r"united states|\busa\b|\bu\.s\.|\bus\b")
PHD = re.compile(r"\bph\.?\s?d\b")
NON_PHD_DEGREE = ["master", "m.s.", "ms in", "ms degree", "ms/phd", "ms or phd",
                  "bachelor", "b.s.", "bs in", "bs/ms", "undergraduate"]
CREDENTIALS = re.compile(r"\b(asa|fsa|maaa|cpa|cfa|cissp|cism|pmp|"
                         r"professional engineer|bar admission|"
                         r"registered nurse|active (?:\w+ )?license)\b")
OPTIONAL_HINTS = ["prefer", "plus", "nice to have", "bonus", "desired",
                  "working toward", "progress toward", "or equivalent"]

MIN_MATCH = {"Target": 75, "Stretch": 75, "Reach": 75, "Long shot": 85}
TIER_POINTS = {"Target": 100, "Stretch": 70, "Reach": 40, "Long shot": 15}


def has_any(text, words):
    return any(w in text for w in words)


def in_us(location):
    """True if the location names the U.S., a state or a big U.S. city."""
    low = location.lower()
    return bool(US_WORDS.search(low) or has_any(low, US_STATES)
                or has_any(low, US_CITIES) or US_ABBR.search(location))


# More countries and big foreign cities, matched as whole words.
FOREIGN_WORDS = re.compile(r"\b(" + "|".join([
    "afghanistan", "albania", "algeria", "angola", "armenia", "azerbaijan", "bahrain",
    "bangladesh", "belarus", "bolivia", "bosnia", "botswana", "bulgaria", "cambodia",
    "cameroon", "croatia", "cyprus", "ecuador", "el salvador", "ethiopia", "ghana",
    "guatemala", "honduras", "iceland", "iran", "iraq", "jamaica", "kazakhstan", "kuwait",
    "kyrgyzstan", "laos", "latvia", "libya", "malta", "mauritius", "moldova", "mongolia",
    "montenegro", "morocco", "mozambique", "myanmar", "namibia", "nepal", "nicaragua",
    "north macedonia", "oman", "pakistan", "paraguay", "peru", "qatar", "rwanda", "senegal",
    "serbia", "slovakia", "slovenia", "sri lanka", "sudan", "tanzania", "tunisia", "uganda",
    "uruguay", "uzbekistan", "venezuela", "zambia", "zimbabwe", "doha", "riyadh", "jeddah",
    "abu dhabi", "cairo", "lagos", "nairobi", "karachi", "lahore", "islamabad", "dhaka",
    "colombo", "kathmandu", "lima", "quito", "montevideo", "cape town", "johannesburg",
    "tallinn", "riga", "vilnius", "sofia", "belgrade", "zagreb", "kyiv", "kiev",
    "amman", "beirut", "casablanca", "almaty", "tbilisi", "yerevan", "baku"]) + r")\b")


def outside_us(location):
    """True only when the location is clearly somewhere else.

    A two-letter code like "IN" alone doesn't count as U.S. when the
    location also names a foreign place (e.g. "Pune, IN")."""
    low = location.lower()
    if not (has_any(low, FOREIGN) or FOREIGN_WORDS.search(low)):
        return False
    strong_us = (US_WORDS.search(low) or has_any(low, US_STATES)
                 or has_any(low, US_CITIES))
    return not strong_us


def is_relevant(job):
    """Quick check on title + location, before fetching descriptions."""
    title = f" {job['title'].lower()} "
    if not has_any(title, ROLE_WORDS) or has_any(title, SKIP_TITLE):
        return False
    return not outside_us(job["location"])


def required_credentials(text):
    """Certifications the job requires (not just prefers)."""
    found = []
    for m in CREDENTIALS.finditer(text):
        window = text[max(0, m.start() - 80): m.end() + 80]
        if not has_any(window, OPTIONAL_HINTS):
            found.append(m.group(1).upper())
    return sorted(set(found))


def knockouts(job):
    """Reasons you would be screened out no matter how good the match is."""
    title = f" {job['title'].lower()} "
    text = job["description"].lower()
    reasons = []
    if outside_us(job.get("location", "")):
        reasons.append(f"Outside the U.S. ({job['location']})")
    if has_any(text, BLOCKERS):
        reasons.append("Requires U.S. citizenship or security clearance")
    if has_any(text, NO_SPONSOR):
        reasons.append("Sponsorship not available")
    if PHD.search(text) and not has_any(text, NON_PHD_DEGREE):
        reasons.append("Requires a PhD")
    creds = required_credentials(text)
    if creds:
        reasons.append("Requires " + ", ".join(creds))
    if has_any(title, LONGSHOT_WORDS):
        reasons.append("Staff/principal/manager level")
    years = years_required(text)
    if years is not None and years >= 8:
        reasons.append(f"Requires {years}+ years of experience")
    return reasons


def years_required(text):
    """Smallest number of years asked for, e.g. '3+ years' -> 3."""
    found = re.findall(r"(\d{1,2})\s*(?:\+|-\s*\d{1,2}|to\s*\d{1,2})?\s*(?:years|yrs)",
                       text.lower())
    return min(int(n) for n in found) if found else None


def tier(job):
    title = f" {job['title'].lower()} "
    if has_any(title, LONGSHOT_WORDS):
        return "Long shot"
    if has_any(title, REACH_WORDS):
        return "Reach"
    if has_any(title, TARGET_WORDS) or re.search(r"\b(i|1)\s*$", title.strip()):
        return "Target"
    years = years_required(job["description"])
    if years is None:
        return "Stretch"
    if years <= 2:
        return "Target"
    return "Stretch" if years <= 5 else "Reach"


def assess(job, ats_percent):
    """Decide tier, sponsorship, blockers and an overall score for one job."""
    text = job["description"].lower()
    job_tier = tier(job)
    blocked = knockouts(job)
    if has_any(text, NO_SPONSOR):
        sponsor, sponsor_points = "❌ no sponsorship", 0
    elif has_any(text, YES_SPONSOR):
        sponsor, sponsor_points = "✅ sponsorship mentioned", 100
    else:
        sponsor, sponsor_points = "❔ not mentioned", 50
    flexible = has_any(text, FLEXIBLE)
    score = round(0.50 * ats_percent + 0.20 * TIER_POINTS[job_tier]
                  + 0.15 * (100 if flexible else 0) + 0.10 * sponsor_points + 5)
    show = not blocked and ats_percent >= MIN_MATCH[job_tier]
    return {"tier": job_tier, "sponsorship": sponsor, "flexible": flexible,
            "blocked": blocked, "score": score, "show": show}