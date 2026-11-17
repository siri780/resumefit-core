"""Evaluation: how well do ResumeFit's safety checks work?

Runs every check on a labelled test set (data/eval/cases.json) and writes
data/eval/REPORT.md with the scores and whether each check meets its pass
rule. No OpenAI calls, so it's free and gives the same result every time.

Each check has "dev" cases (used while building it) and "holdout" cases
(written up front and never used for tuning), so the holdout score is the
honest one.

    python -m app.evaluate
"""
import json
from datetime import date
from pathlib import Path

from app.ats import ROOT, find_skills, latex_to_text, load_skills

CASES = ROOT / "data" / "eval" / "cases.json"
REPORT = ROOT / "data" / "eval" / "REPORT.md"

# (metric, comparison, threshold): the pass rules for each check
RULES = {
    "posting_guard": [("catch rate", ">=", 0.90), ("false alarm rate", "<=", 0.05)],
    "edit_guard": [("catch rate", ">=", 1.00), ("wrongly blocked", "<=", 0.10)],
    "letter_guard": [("catch rate", ">=", 0.95), ("wrongly removed", "<=", 0.10)],
    "email_reader": [("accuracy", ">=", 0.90)],
    "applied_match": [("accuracy", ">=", 0.95)],
}
TITLES = {
    "posting_guard": "Posting guard: hidden instructions to AI in job postings",
    "edit_guard": "Resume-edit guard: made-up numbers/skills, lost keywords, broken LaTeX",
    "letter_guard": "Cover-letter guard: sentences with facts not on the resume",
    "email_reader": "Email reader: applied / interview / rejected",
    "applied_match": "Already-applied match: same job vs a different one",
}


def resume_facts():
    """Skills and text across all three base resumes."""
    text = " ".join(latex_to_text((ROOT / "data" / f"resume_{k}.tex").read_text(encoding="utf-8"))
                    for k in ("ds", "mle", "swe"))
    skills = load_skills()
    return text, find_skills(text, skills), skills


def predict(check, case, facts):
    """What the check says for one case."""
    text, resume_skills, skills = facts
    if check == "posting_guard":
        from app.posting_guard import inspect
        return "flag" if inspect(case["text"]) else "clean"
    if check == "edit_guard":
        from app.guard import check_bullet
        return "block" if check_bullet(case["original"], case["new"], resume_skills, skills) else "ok"
    if check == "letter_guard":
        from app.cover_letter import sentence_problems
        from app.guard import numbers_in
        problems = sentence_problems(case["sentence"], numbers_in(text), resume_skills, skills)
        return "remove" if problems else "keep"
    if check == "email_reader":
        from app.app_emails import classify
        return str(classify(case["subject"], case["body"]))
    if check == "applied_match":
        from app.applications import applied_before, applied_keys
        keys = applied_keys([{"company": case["tracker"][0], "role": case["tracker"][1]}])
        hit = applied_before({"company": case["job"][0], "title": case["job"][1]}, keys)
        return "same" if hit else "different"
    raise ValueError(check)


POSITIVE = {"posting_guard": ("flag", "clean"), "edit_guard": ("block", "ok"),
            "letter_guard": ("remove", "keep")}
NEGATIVE_NAME = {"posting_guard": "false alarm rate", "edit_guard": "wrongly blocked",
                 "letter_guard": "wrongly removed"}


def metrics(check, results):
    """results: list of (expected, predicted)."""
    if check in POSITIVE:
        bad, good = POSITIVE[check]
        bad_cases = [(e, p) for e, p in results if e == bad]
        good_cases = [(e, p) for e, p in results if e == good]
        return {
            "catch rate": sum(p == bad for _, p in bad_cases) / max(len(bad_cases), 1),
            NEGATIVE_NAME[check]: sum(p == bad for _, p in good_cases) / max(len(good_cases), 1),
        }
    return {"accuracy": sum(e == p for e, p in results) / max(len(results), 1)}


def passes(value, op, threshold):
    return value >= threshold if op == ">=" else value <= threshold


def run():
    """Returns {check: {"dev": metrics, "holdout": metrics, "misses": [...], "pass": bool}}."""
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    facts = resume_facts()
    report = {}
    for check, items in cases.items():
        by_split = {"dev": [], "holdout": []}
        misses = []
        for case in items:
            got = predict(check, case, facts)
            by_split[case["split"]].append((case["expect"], got))
            if got != case["expect"]:
                misses.append((case["id"], case["split"], case["expect"], got))
        scores = {s: metrics(check, r) for s, r in by_split.items()}
        everything = metrics(check, by_split["dev"] + by_split["holdout"])
        ok = all(passes(everything[m], op, t) for m, op, t in RULES[check])
        report[check] = {**scores, "all": everything, "misses": misses, "pass": ok,
                         "count": {s: len(r) for s, r in by_split.items()}}
    return report


def pct(x):
    return f"{x:.0%}"


def write_report(report):
    lines = [f"# ResumeFit evaluation ({date.today():%b %d, %Y})", "",
             "Every safety check run on a labelled test set. **Holdout** cases were written",
             "before tuning and never used to adjust the checks, so they're the honest score.",
             "No AI calls: same result every run. Re-run with `python -m app.evaluate`.", "",
             "| Check | Cases (dev + holdout) | Pass rule | Dev | Holdout | Result |",
             "|---|---|---|---|---|---|"]
    for check, r in report.items():
        rules = "; ".join(f"{m} {op} {pct(t)}" for m, op, t in RULES[check])
        dev = ", ".join(f"{m} {pct(v)}" for m, v in r["dev"].items())
        hold = ", ".join(f"{m} {pct(v)}" for m, v in r["holdout"].items())
        lines.append(f"| {TITLES[check]} | {r['count']['dev']} + {r['count']['holdout']} | {rules} "
                     f"| {dev} | {hold} | {'✅ pass' if r['pass'] else '❌ fail'} |")
    misses = [(c, m) for c, r in report.items() for m in r["misses"]]
    lines += ["", "## Misses", ""]
    lines += ([f"- `{c}` {cid} ({split}): expected **{e}**, got **{g}**"
               for c, (cid, split, e, g) in misses] or ["None."])
    lines += ["", "## Known limitations (found by this evaluation)", "",
              "1. **Tools that aren't on the skill list slip through.** The guards recognise "
              "skills from `data/skills.csv`, so a made-up tool that isn't on it (e.g. "
              "\"Great Expectations\") passes. Next step: flag capitalised tool-like names "
              "that don't appear on the resume, and keep growing the skill list.",
              "2. **A real number can be reused in a false claim.** \"Improved revenue by 25%\" "
              "passes because 25% is on the resume (CUPED variance reduction). Next step: "
              "check the words next to each number, not just the number.",
              "",
              "Fixed after the first run: short bullets were wrongly blocked for length; "
              "\"recommenders\" wasn't counted as Recommendation Systems; Snowflake was "
              "counted as Data Warehousing; \"3 million\" passed because \"3\" was on the "
              "resume. Holdout cases used for those fixes were moved to dev and replaced "
              "with fresh ones."]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return REPORT


if __name__ == "__main__":
    results = run()
    path = write_report(results)
    for check, r in results.items():
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {check:14} dev={r['dev']}  holdout={r['holdout']}")
    print(f"Report: {path}")
