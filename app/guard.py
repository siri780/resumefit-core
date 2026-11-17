import re

from app.ats import find_skills, latex_to_text

NUMBER = re.compile(r"\d+(?:[.,]\d+)*(?:\s?(?:million|billion|thousand|[kmb])(?![a-z]))?", re.I)
SHORT = {"thousand": "k", "million": "m", "billion": "b"}


def numbers_in(text):
    """Return the set of numbers in text, e.g. {'40', '5863', '92.07', '14m'}.

    '3 million' and '14M' keep their size ('3m', '14m'), so '3 million
    patients' doesn't pass just because '3' appears elsewhere on the resume.
    """
    found = set()
    for n in NUMBER.findall(text):
        n = n.replace(",", "").replace(" ", "").lower()
        for word, letter in SHORT.items():
            n = n.replace(word, letter)
        found.add(n)
    return found


def check_numbers(original, new):
    """Every number in the new bullet must already be in the original."""
    added = numbers_in(new) - numbers_in(original)
    if added:
        return [f"New number(s) not in original: {', '.join(sorted(added))}"]
    return []


def check_skills(new, resume_skills, skills):
    """The new bullet must not add skills that are not on the resume."""
    added = find_skills(latex_to_text(new), skills) - resume_skills
    if added:
        return [f"New skill(s) not on resume: {', '.join(sorted(added))}"]
    return []


def check_latex(new):
    """Special characters must be escaped and braces balanced."""
    problems = []
    for ch in "%&#$_":
        if re.search(r"(?<!\\)" + re.escape(ch), new):
            problems.append(f"Unescaped '{ch}' (write \\{ch})")
    if new.count("{") != new.count("}"):
        problems.append("Unbalanced braces { }")
    return problems


def check_length(original, new, max_ratio=1.25, slack=30):
    """The new bullet can be at most 25% longer than the original (short
    bullets may grow by up to 30 characters, about 5 words)."""
    if len(new) > max(len(original) * max_ratio, len(original) + slack):
        return [f"Too long: {len(new)} vs {len(original)} characters"]
    return []


def check_keyword_loss(original, new, skills):
    """The new bullet must keep every skill keyword the original had."""
    lost = (find_skills(latex_to_text(original), skills)
            - find_skills(latex_to_text(new), skills))
    if lost:
        return [f"Removed keyword(s): {', '.join(sorted(lost))}"]
    return []


def check_bullet(original, new, resume_skills, skills):
    """Run all 5 checks. An empty list means the bullet is safe."""
    return (check_numbers(original, new)
            + check_skills(new, resume_skills, skills)
            + check_keyword_loss(original, new, skills)
            + check_latex(new)
            + check_length(original, new))
