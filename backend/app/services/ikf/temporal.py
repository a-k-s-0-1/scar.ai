"""Temporal evidence — when a claim was true, and how much that still matters.

Two claims can look like a contradiction and be nothing of the sort: "market share
was 65%" (2024) and "market share is 71%" (2026) is the same fact moving, not two
sources disagreeing. Versioning therefore needs each claim's own validity window
before it can tell the two apart.

Everything here is best-effort text extraction on a *pure* function so it can be
tested without a database or a model, and so a claim with no parseable date degrades
to "unknown" instead of being silently treated as current.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

# Where a technology or market fact is roughly half as relevant again.
# ~18 months is the point most of the fast-moving domains in the research set move
# on; a longer half-life would keep stale numbers looking load-bearing.
HALF_LIFE_DAYS = 540
# A source with no date is neither fresh nor stale, so it sits above the floor but
# well below a dated recent one.
UNKNOWN_DATE_SCORE = 0.6
MIN_RECENCY = 0.05
MAX_RECENCY = 1.0

_YEAR = r"(?:19\d{2}|20\d{2})"

_RANGE_RE = re.compile(
    rf"\b(?:between|from)\s+({_YEAR})\s+(?:and|to|through|until|[-–—])\s+({_YEAR})\b",
    re.IGNORECASE,
)
_QUARTER_RE = re.compile(rf"\bQ([1-4])\s*(?:of\s*)?({_YEAR})\b", re.IGNORECASE)
_MONTH_RE = re.compile(
    rf"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    rf"aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+({_YEAR})\b",
    re.IGNORECASE,
)
_SINCE_RE = re.compile(
    rf"\b(?:since|as of|after|starting|starting in)\s+({_YEAR})\b", re.IGNORECASE
)
_UNTIL_RE = re.compile(
    rf"\b(?:by|before|until|through|up to)\s+({_YEAR})\b", re.IGNORECASE
)
_BARE_YEAR_RE = re.compile(rf"\b({_YEAR})\b")


@dataclass(frozen=True)
class ValidityWindow:
    """The period a claim is asserted to hold for. ``None`` means unbounded/unknown."""

    start: int | None = None
    end: int | None = None
    precision: str = "unknown"  # year | quarter | month | unknown

    @property
    def known(self) -> bool:
        return self.start is not None or self.end is not None

    @property
    def year(self) -> int | None:
        """The point in time the claim speaks about: its end if bounded, else start."""
        return self.end if self.end is not None else self.start

    def overlaps(self, other: ValidityWindow) -> bool:
        """Whether the two windows share any year."""
        left_start = self.start if self.start is not None else self.end
        left_end = self.end if self.end is not None else self.start
        right_start = other.start if other.start is not None else other.end
        right_end = other.end if other.end is not None else other.start
        if None in (left_start, left_end, right_start, right_end):
            return False
        return not (left_end < right_start or right_end < left_start)


UNKNOWN_WINDOW = ValidityWindow()


def extract_validity_window(
    text: str, fallback_year: int | None = None
) -> ValidityWindow:
    """Parse the period a claim speaks about, or fall back to the claim's own date.

    Order matters: an explicit range wins over a lone year, because "between 2019 and
    2021" would otherwise collapse to whichever year the scan hit first.
    """
    haystack = text or ""

    match = _RANGE_RE.search(haystack)
    if match:
        first, second = int(match.group(1)), int(match.group(2))
        return ValidityWindow(min(first, second), max(first, second), "year")

    match = _QUARTER_RE.search(haystack)
    if match:
        year = int(match.group(2))
        return ValidityWindow(year, year, "quarter")

    match = _SINCE_RE.search(haystack)
    if match:
        return ValidityWindow(int(match.group(1)), None, "year")

    match = _UNTIL_RE.search(haystack)
    if match:
        return ValidityWindow(None, int(match.group(1)), "year")

    match = _MONTH_RE.search(haystack)
    if match:
        year = int(match.group(1))
        return ValidityWindow(year, year, "month")

    match = _BARE_YEAR_RE.search(haystack)
    if match:
        year = int(match.group(1))
        return ValidityWindow(year, year, "year")

    if fallback_year is not None:
        return ValidityWindow(fallback_year, fallback_year, "year")

    return UNKNOWN_WINDOW


def recency_score(
    published_at: datetime | None,
    now: datetime | None = None,
    half_life_days: int = HALF_LIFE_DAYS,
) -> float:
    """Exponential decay on how old a source is, in ``[MIN_RECENCY, MAX_RECENCY]``.

    A future-dated source (clock skew, mis-parsed date) clamps to the maximum rather
    than scoring above it.
    """
    if published_at is None:
        return UNKNOWN_DATE_SCORE

    reference = now or datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)

    age_days = max(0.0, (reference - published_at).total_seconds() / 86_400)
    decayed = 0.5 ** (age_days / half_life_days)
    return max(MIN_RECENCY, min(MAX_RECENCY, decayed))


def temporal_relation(left: ValidityWindow, right: ValidityWindow) -> str:
    """Classify two windows as concurrent, ordered, or not comparable.

    Returns ``"same"``, ``"left_newer"``, ``"right_newer"`` or ``"unknown"``. This is
    the single decision that separates claim *versioning* from a real contradiction.
    """
    if not left.known or not right.known:
        return "unknown"
    if left.overlaps(right):
        return "same"

    left_year = left.year or 0
    right_year = right.year or 0
    if left_year == right_year:
        # Same year but non-overlapping ranges cannot happen; be conservative.
        return "unknown"
    return "left_newer" if left_year > right_year else "right_newer"
