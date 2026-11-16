"""Keep every tailored resume to exactly one page, keeping all the edits.

If the AI's edits push the resume onto a second page, tighten the layout a
little at a time (more page height, tighter bullet spacing, slightly wider
lines, tighter section spacing, slightly tighter line spacing) until it fits.
Only if even the tightest layout overflows are edits undone, longest first,
so the result is always one page.
"""
import re

import pdfplumber

from app.latex_io import apply_edits

# Each step is (pattern, replacement); steps are cumulative.
SQUEEZE_STEPS = [
    [(r"\\addtolength\{\\topmargin\}\{-0\.6in\}", r"\\addtolength{\\topmargin}{-0.7in}"),
     (r"\\addtolength\{\\textheight\}\{1\.2in\}", r"\\addtolength{\\textheight}{1.4in}")],
    [(r"(\\newcommand\{\\resumeItem\}\[1\]\{\\item\\small\{\{#1 \\vspace\{)-3pt",
      r"\g<1>-4pt"),
     (r"(\\newcommand\{\\resumeItemListEnd\}\{\\end\{itemize\}\\vspace\{)-5pt",
      r"\g<1>-6pt")],
    [(r"\\addtolength\{\\oddsidemargin\}\{-0\.55in\}", r"\\addtolength{\\oddsidemargin}{-0.65in}"),
     (r"\\addtolength\{\\evensidemargin\}\{-0\.55in\}", r"\\addtolength{\\evensidemargin}{-0.65in}"),
     (r"\\addtolength\{\\textwidth\}\{1\.1in\}", r"\\addtolength{\\textwidth}{1.3in}")],
    [(r"(\\titleformat\{\\section\}\{\s*\\vspace\{)-5pt", r"\g<1>-7pt")],
    [(r"\\begin\{document\}", r"\\linespread{0.97}\\selectfont\n\\begin{document}")],
]


def squeeze(tex, level):
    """The resume with the first `level` tightening steps applied."""
    for step in SQUEEZE_STEPS[:level]:
        for pattern, repl in step:
            tex = re.sub(pattern, repl, tex, count=1)
    return tex


def page_count(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages)


def growth(edit):
    """How much longer an edit makes its bullet."""
    return len(edit["new"]) - len(edit["original"])


def fit_one_page(tex, edits, build, name, count=page_count):
    """Keep all edits on one page if any layout allows it.
    Returns (new_tex, pdf_path, kept_edits, dropped_edits)."""
    kept, dropped = list(edits), []
    while True:
        edited = apply_edits(tex, {e["id"]: e["new"] for e in kept})
        for level in range(len(SQUEEZE_STEPS) + 1):
            new_tex = squeeze(edited, level)
            pdf = build(name, tex=new_tex)
            if count(pdf) <= 1:
                return new_tex, pdf, kept, dropped
        if not kept:                      # the base resume itself is too long
            return new_tex, pdf, kept, dropped
        longest = max(kept, key=growth)
        kept.remove(longest)
        dropped.append(longest)
