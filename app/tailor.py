
import os

from openai import OpenAI
from pydantic import BaseModel

from app.ats import ROOT, find_skills, latex_to_text, load_skills, score
from app.guard import check_bullet
from app.latex_io import get_bullets

MODEL = os.getenv("RESUMEFIT_MODEL", "gpt-6.1-sol")

RULES = """You tailor resume bullets to a job description. Strict rules:
1. Only reword the bullets given. Never invent facts.
2. Keep every number exactly as written. Never add new numbers.
3. Never add a tool, skill, company or method that is not already in
   the original bullet or in the candidate's skill list.
4. Use job-description keywords only where the original bullet
   honestly supports them.
5. Keep LaTeX escapes exactly: write \\% and \\& (never bare % or &).
6. Start with a strong action verb. Keep length similar to the original.
7. If a bullet cannot be honestly improved, do not include it.
8. Keep the original verb tense (present tense for current roles)."""


class Suggestion(BaseModel):
    bullet_id: int
    new_text: str
    reason: str


class Suggestions(BaseModel):
    suggestions: list[Suggestion]


def suggest_edits(bullets, jd, allowed_skills, missing):
    """Ask the AI for bullet rewrites. Returns a list of Suggestion."""
    client = OpenAI()
    listing = "\n".join(f"{i}: {b['text']}" for i, b in enumerate(bullets)
                        if b["section"] != "Education")
    prompt = (f"JOB DESCRIPTION:\n{jd}\n\n"
              f"CANDIDATE SKILL LIST: {', '.join(sorted(allowed_skills))}\n"
              f"JOB KEYWORDS MISSING FROM RESUME: {', '.join(missing)}\n\n"
              f"BULLETS (id: text):\n{listing}")
    response = client.responses.parse(
        model=MODEL,
        input=[{"role": "system", "content": RULES},
               {"role": "user", "content": prompt}],
        text_format=Suggestions,
    )
    return response.output_parsed.suggestions


APPROVED_FILE = ROOT / "data" / "approved_skills.txt"


def load_approved():
    """Skills you have approved as honest, one per line."""
    if not APPROVED_FILE.exists():
        return set()
    lines = APPROVED_FILE.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip()}


def tailor(bullets, jd, resume_skills, skills, missing):
    """Get AI suggestions and run every one through the guard."""
    from app.posting_guard import sanitize
    jd = sanitize(jd)                 # never let hidden AI instructions through
    allowed = resume_skills | load_approved()
    results = []
    for s in suggest_edits(bullets, jd, allowed, missing):
        if not 0 <= s.bullet_id < len(bullets):
            continue
        original = bullets[s.bullet_id]["text"]
        results.append({
            "id": s.bullet_id,
            "original": original,
            "new": s.new_text,
            "reason": s.reason,
            "problems": check_bullet(original, s.new_text, allowed, skills),
        })
    return results


if __name__ == "__main__":
    tex = (ROOT / "data" / "resume_ds.tex").read_text(encoding="utf-8")
    jd = (ROOT / "data" / "sample_jd.txt").read_text(encoding="utf-8")
    skills = load_skills()
    resume_skills = find_skills(latex_to_text(tex), skills)
    missing = score(latex_to_text(tex), jd, skills)["missing"]
    for r in tailor(get_bullets(tex), jd, resume_skills, skills, missing):
        status = "BLOCKED" if r["problems"] else "OK"
        print(f"\n[{status}] bullet {r['id']}")
        print("  OLD:", r["original"])
        print("  NEW:", r["new"])
        print("  WHY:", r["reason"])
        for p in r["problems"]:
            print("  !!", p)


def save_approved(skills):
    """Save approved skills to the file, one per line."""
    text = "".join(f"{s}\n" for s in sorted(skills))
    APPROVED_FILE.write_text(text, encoding="utf-8")