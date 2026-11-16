"""Turn a cover letter's text into a one-page PDF with the resume's header."""
import re

from app.build_pdf import build_pdf

SPECIAL = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
           "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
           "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}

TEMPLATE = r"""\documentclass[11pt,letterpaper]{article}
\usepackage[margin=1in]{geometry}
\usepackage[hidelinks]{hyperref}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{textcomp}
\setlength{\parindent}{0pt}
\setlength{\parskip}{10pt}
\pagestyle{empty}
\begin{document}
{\LARGE\bfseries Shirisha Gajendra}\\[3pt]
{\footnotesize {{PHONE}} $|$ \href{mailto:{{EMAIL}}}{{{EMAIL}}} $|$
\href{https://www.linkedin.com/in/shirisha-gajendra}{in/shirisha-gajendra} $|$
\href{https://github.com/siri780}{github.com/siri780} $|$
\href{https://siri780.github.io}{Portfolio} $|$ New York, NY}

\vspace{6pt}
BODY
\end{document}
"""


def escape(text):
    """Make plain text safe for LaTeX."""
    text = re.sub(r"[\\&%$#_{}~^]", lambda m: SPECIAL[m.group()], text)
    return (text.replace("—", "---").replace("–", "--")
            .replace("’", "'").replace("‘", "`")
            .replace("“", "``").replace("”", "''"))


def letter_tex(letter):
    """The LaTeX source for a letter. Paragraphs are separated by blank lines;
    a single newline inside a paragraph (like 'Sincerely,\\nName') is kept."""
    paragraphs = [p.strip() for p in letter.split("\n\n") if p.strip()]
    body = "\n\n".join(escape(p).replace("\n", "\\\\\n") for p in paragraphs)
    return TEMPLATE.replace("BODY", body)


def safe_name(company):
    return re.sub(r"[^A-Za-z0-9]+", "_", company).strip("_") or "Company"


def build_letter_pdf(letter, company):
    """Compile the letter and return the PDF path."""
    return build_pdf(f"Shirisha_Gajendra_Cover_Letter_{safe_name(company)}",
                     tex=letter_tex(letter))
