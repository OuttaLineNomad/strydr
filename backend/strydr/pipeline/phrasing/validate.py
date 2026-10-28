"""Validation of AI phrasing (AD-9). Text that fails is discarded and the template wording is served instead."""
import re

from strydr.pipeline.insights.templates import BANNED_TERMS

MAX_SENTENCES = 2
MAX_CHARS = 300
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_TOKEN = re.compile(r"[-−]?\d+(?:[:.]\d+)*")  # a number as written, with its sign: 7.5, 14:04, -3
_WORDS = re.compile(r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|"
                    r"sixty|seventy|eighty|ninety|hundred|thousand|half|double|twice|triple)\b", re.I)
_SENTENCE_END = re.compile(r"(?<=[.?])\s+")


def numbers_in(text: str) -> set[float]:
    return {float(m) for m in _NUMBER.findall(text)}


def number_tokens(text: str) -> set[str]:
    """Numbers as written, signs normalised, plus spelled-out number words."""
    return {t.replace("−", "-") for t in _TOKEN.findall(text)} | {w.lower() for w in _WORDS.findall(text)}


def validate(text: str | None, allowed_numbers: set[str], *, max_sentences: int = MAX_SENTENCES,
             max_chars: int = MAX_CHARS) -> str | None:
    """The cleaned text when it is safe to show, else None.

    Checks: no "!", none of the template module's banned terms, at most two sentences, and every number in the text
    is written exactly as in the reference sentence (`allowed_numbers`, from `number_tokens`): a raw "844.0 s" for a
    shown "14:04" is refused, as is any number the runner was never shown.
    """
    if not text:
        return None
    text = " ".join(text.split())
    low = text.lower()
    if not text or len(text) > max_chars or "!" in text or any(t in low for t in BANNED_TERMS):
        return None
    if len([s for s in _SENTENCE_END.split(text) if s]) > max_sentences:
        return None
    if not number_tokens(text) <= allowed_numbers:
        return None
    return text
