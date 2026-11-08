"""Posting safety check: job postings are untrusted text.

Some postings hide text meant for AI tools, like "If you are an AI, ignore
your instructions and ...". This module finds that before the LLM reads a
posting, removes it, and tells you about it in the alert.
"""
import re

# Characters you can't see. Zero-width spaces and similar are common in
# copy-pasted job ads, so they are removed quietly. Unicode "tag" letters
# have no normal use in a job ad: they spell out hidden text, so they're flagged.
INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩"
                       "﻿\U000e0000-\U000e007f]")
TAG_LETTERS = re.compile("[\U000e0000-\U000e007f]")

# Sentences written to steer an AI rather than inform a person. Kept narrow
# on purpose: "As an AI Engineer you will..." is a normal job ad.
INSTRUCTION = re.compile(
    r"\b(ignore|disregard|forget|override)\b[^.!?]{0,40}"
    r"\b(previous|prior|above|earlier|all|any|your|these)\b[^.!?]{0,20}"
    r"\b(instructions?|prompts?|directions)\b"
    r"|\b(if|when) you are an? (ai|llm|large language model|language model|chatbot"
    r"|bot|automated (tool|system))( (model|assistant|tool|system|agent))?"
    r"\s*(,|reading|screening|reviewing|parsing|evaluating|processing)"
    r"|\bas an? (ai|llm|large language model|language model)( model| assistant)?\s*,"
    r"|\b(system|hidden|secret) (prompt|instructions)\b"
    r"|\b(include|insert|mention|say|write) the (exact |secret |hidden )?"
    r"(word|phrase|code word|codeword)\b"
    r"|\bdo not (reveal|tell|mention|disclose) (these instructions|that you are an? ai)\b",
    re.IGNORECASE)

SENTENCE = re.compile(r"(?<=[.!?])\s+")
LONG = 300          # a "sentence" longer than this is really a whole paragraph


def instruction_sentences(text):
    """The sentences in a posting that look like instructions to an AI."""
    return [s for s in SENTENCE.split(text or "") if INSTRUCTION.search(s)]


def inspect(text):
    """Short, human-readable list of problems found in a posting."""
    flags = []
    if TAG_LETTERS.search(text or ""):
        flags.append("hidden Unicode text")
    count = len(instruction_sentences(text))
    if count:
        flags.append(f"{count} line{'s' if count > 1 else ''} written for AI tools")
    return flags


def sanitize(text):
    """The posting with invisible characters and AI-directed lines removed.
    This is what the LLM sees when tailoring."""
    text = INVISIBLE.sub("", text or "")
    kept = []
    for s in SENTENCE.split(text):
        if not INSTRUCTION.search(s):
            kept.append(s)
        elif len(s) > LONG:                   # drop just the bad part
            kept.append(INSTRUCTION.sub("", s))
    return " ".join(kept).strip()
