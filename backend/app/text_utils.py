"""Small text helpers used for claim checking and keyword extraction.

These are deliberately simple, deterministic and easy to test. They are
heuristics, not proof of meaning: they catch missing sources, numbers that do
not appear in the cited abstract, and claims with little vocabulary in common
with their sources.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

STOPWORDS = frozenset(
    """a about above after again against all also am an and any are as at be because been before
    being below between both but by can could did do does doing down during each few for from further
    had has have having he her here hers him his how i if in into is it its just may me might more most
    my no nor not now of off on once only or other our out over own same she should so some such than
    that the their them then there these they this those through to too under until up very was we were
    what when where which while who whom why will with would you your whats evidence effect effects
    impact impacts relationship association associated link linked role question research studies study
    among versus vs good bad many much work works help helps use used using people""".split()
)

CITE_RE = re.compile(r"\[(S\d+(?:\s*,\s*S\d+)*)\]")
_WORD_RE = re.compile(r"[a-z][a-z0-9]+")
_NUM_RE = re.compile(r"(?<![A-Za-z0-9_])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(\s*%)?")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[\"'(*#\-])")
_SUFFIXES = ("ations", "ation", "ings", "ing", "edly", "ed", "ies", "es", "s", "ly")

# Numbers that are formatting, not claims (durations, timestamps, hashtags, scene labels).
_NONCLAIM_RE = re.compile(
    r"(\b\d{1,2}:\d{2}\b)"
    r"|(\b\d+(?:\s*[-–]\s*\d+)?\s*(?:seconds?|secs?|minutes?|mins?|words?|characters?|chars?)\b)"
    r"|(#\w+)"
    r"|(\b(?:scene|post|part|step|option|slide)\s+\d+\b)",
    re.IGNORECASE,
)


def tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            word = word[: -len(suffix)]
            break
    return word[:5]


def content_stems(text: str) -> set[str]:
    return {stem(w) for w in tokenize(text) if w not in STOPWORDS and len(w) >= 3}


def extract_keywords(question: str, limit: int = 6) -> list[str]:
    seen: list[str] = []
    for word in tokenize(question):
        if word in STOPWORDS or len(word) < 3 or word in seen:
            continue
        seen.append(word)
    return seen[:limit]


def lexical_overlap(claim: str, source_text: str) -> float:
    """Share of the claim's content words (stemmed) that also appear in the source text."""
    claim_stems = content_stems(claim)
    if not claim_stems:
        return 0.0
    return len(claim_stems & content_stems(source_text)) / len(claim_stems)


def split_sentences(text: str) -> list[str]:
    parts: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            parts.extend(s.strip() for s in _SENTENCE_RE.split(line) if s.strip())
    return parts


def _normalise_number(raw: str) -> str:
    try:
        return format(Decimal(raw.replace(",", "")).normalize(), "f")
    except InvalidOperation:  # pragma: no cover - regex only passes valid numbers
        return raw


def all_numbers(text: str) -> set[str]:
    """Every number in the text, normalised (so '1,200' == '1200' and '45.0' == '45')."""
    return {_normalise_number(m.group(1)) for m in _NUM_RE.finditer(text)}


def find_statistics(text: str) -> set[str]:
    """Numbers that look like statistics: percentages, decimals, and integers >= 10 that are not years."""
    stats: set[str] = set()
    for match in _NUM_RE.finditer(text):
        raw, percent = match.group(1), match.group(2)
        if percent or "." in raw:
            stats.add(_normalise_number(raw))
            continue
        value = int(raw.replace(",", ""))
        if 1900 <= value <= 2100:
            continue
        if value >= 10:
            stats.add(_normalise_number(raw))
    return stats


def strip_nonclaim_numbers(text: str) -> str:
    return _NONCLAIM_RE.sub(" ", text)


def strip_citations(text: str) -> str:
    return CITE_RE.sub(" ", text)


def extract_citation_ids(text: str) -> list[str]:
    ids: list[str] = []
    for match in CITE_RE.finditer(text):
        ids.extend(part.strip() for part in match.group(1).split(","))
    return ids


def shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return cut.rstrip(",;:- ") + "…"
