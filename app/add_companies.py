"""Try each candidate company's job board and add the ones that work.

Run in the codespace:  python -m app.add_companies
Each candidate lists one or more guesses for its board name; the first guess
that returns jobs is added to data/companies.csv. Candidates that fail are
listed so you can see what was skipped.
"""
import csv

from app.feeds import COMPANIES_FILE, READERS, load_companies

CANDIDATES = COMPANIES_FILE.parent / "company_candidates.csv"


def try_candidate(company, source, slugs):
    """Return (slug, number_of_jobs) for the first working board, or None."""
    for slug in slugs:
        try:
            jobs = READERS[source](company, slug)
        except Exception:
            continue
        if jobs:
            return slug, len(jobs)
    return None


def main():
    existing = {c["company"].lower() for c in load_companies()}
    with open(CANDIDATES, encoding="utf-8") as f:
        candidates = list(csv.DictReader(f))
    added, skipped = [], []
    for c in candidates:
        if c["company"].lower() in existing:
            continue
        found = try_candidate(c["company"], c["source"], c["slugs"].split("|"))
        if found:
            added.append((c["company"], c["source"], found[0]))
            print(f"✅ {c['company']}: {found[1]} jobs ({c['source']}/{found[0]})", flush=True)
        else:
            skipped.append(c["company"])
            print(f"❌ {c['company']}: no working board found", flush=True)
    if added:
        with open(COMPANIES_FILE, "a", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(added)
    print(f"\nAdded {len(added)} companies; skipped {len(skipped)}: {', '.join(skipped)}")


if __name__ == "__main__":
    main()
