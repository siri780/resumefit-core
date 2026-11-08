"""Posting safety check: job postings are untrusted text.

Some postings hide text meant for AI tools, like "If you are an AI, ignore
your instructions and ...". This module finds that before the LLM reads a
posting, removes it, and tells you about it in the alert.
"""
import re

# Characters you can't see: zero-width spaces/joiners, word joiners,
# byte-order marks, bidirectional controls and Unicode "tag" letters.
INVISIBLE = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069"
                       "\ufeff\U000e0000-\U000e007f]")

# "As an AI engineer..." is a normal job ad, not an instruction.
NOT_A_ROLE = (r"(?![\s-]+(engineer|engineering|researcher|research|scientist|developer"
              r"|specialist|architect|lead|leader|product|products|team|teams|company"
              r"|platform|startup|first|native|expert|practitioner|enthusiast|tools?"
              r"|systems?|solutions?|models?|infrastructure|applications?|ops)\b)")

# Sentences written to steer an AI rather than inform a person.
INSTRUCTION = re.compile(
    r"\b(ignore|disregard|forget|override)\b[^.!?]{0,40}"
    r"\b(previous|prior|above|earlier|all|any|your|these)\b[^.!?]{0,20}"
    r"\b(instructions?|prompts?|rules|directions|guidelines)\b"
    r"|\b(if|when) you are an? (ai|a\.i\.|llm|large language model|language model"
    r"|chatbot|bot|assistant|gpt|automated (tool|system))\b" + NOT_A_ROLE +
    r"|\bas an? (ai|llm|large language model|language model)\b" + NOT_A_ROLE +
    r"|\b(system|hidden|secret) (prompt|instructions?|message)\b"
    r"|\b(include|insert|add|use|mention|say|write) the (exact )?"
    r"(word|phrase|keyword|code word|codeword)\b"
    r"|\bdo not (reveal|tell|mention|disclose) (this|that you|these instructions)\b",
    re.IGNORECASE)

# HTML tricks that hide text from people but not from programs.
HIDDEN_HTML = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(px|pt|em)?\s*[;\"']"
    r"|color\s*:\s*(#fff\b|#ffffff\b|white\b)|opacity\s*:\s*0\s*[;\"']",
    re.IGNORECASE)

SENTENCE = re.compile(r"(?<=[.!?])\s+")


def has_hidden_html(raw):
    """True if the raw HTML of a posting hides some of its text."""
    return bool(HIDDEN_HTML.search(raw or ""))


def instruction_sentences(text):
    """The sentences in a posting that look like instructions to an AI."""
    return [s for s in SENTENCE.split(text or "") if INSTRUCTION.search(s)]


def inspect(text, hidden_html=False):
    """Short, human-readable list of problems found in a posting."""
    flags = []
    if INVISIBLE.search(text or ""):
        flags.append("invisible characters")
    if hidden_html:
        flags.append("text hidden with HTML styling")
    count = len(instruction_sentences(text))
    if count:
        flags.append(f"{count} line{'s' if count > 1 else ''} written for AI tools")
    return flags


def sanitize(text):
    """The posting with invisible characters and AI-directed lines removed.
    This is what the LLM sees when tailoring."""
    text = INVISIBLE.sub("", text or "")
    kept = [s for s in SENTENCE.split(text) if not INSTRUCTION.search(s)]
    return " ".join(kept).strip()
