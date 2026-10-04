"""Claim versioning — the same fact moving through time is not a contradiction.

"IKF 1.0" flagged any two claims on the same subject+predicate with different values
as a conflict. That is wrong often enough to matter: most such pairs are the *same*
fact observed at two dates, and reporting them as disagreement buries the real ones.

This module turns a flat claim list into version groups. Each group knows its ordered
history, which claims genuinely conflict (same period, incompatible value), and which
are merely successive readings. It is pure and DB-free on purpose: the caller decides
how claims and sources are fetched, the maths here stays testable in isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher

from app.services.ikf.temporal import UNKNOWN_WINDOW, ValidityWindow, temporal_relation

# Two values this similar are restatements, not disagreement ("71%" vs "71.0%").
VALUE_SIMILARITY_FLOOR = 0.6
# Numeric values within 2% of each other are the same number reported twice, which
# absorbs rounding while still catching 65% vs 71%.
NUMERIC_EQUALITY_TOLERANCE = 0.02

_VALUE_NOISE = re.compile(r"[\s,]+")
_PERCENT_WORDS = re.compile(r"\b(?:per\s?cent|percent|percentage)\b", re.IGNORECASE)
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass
class ClaimVersion:
    """One observation of a subject/predicate pair, pinned to a point in time."""

    claim_id: str
    text: str
    #: Canonical, resolver-normalized subject and predicate.
    subject: str
    predicate: str
    value: str = ""
    window: ValidityWindow = UNKNOWN_WINDOW
    confidence: str = "medium"
    extracted_at: datetime | None = None
    source_ids: list[str] = field(default_factory=list)
    #: Evidence strength, when the caller has scored it; decides the group's winner.
    strength: float | None = None

    @property
    def group_key(self) -> tuple[str, str]:
        return (self.subject, self.predicate)

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "subject": self.subject,
            "predicate": self.predicate,
            "value": self.value,
            "valid_from": self.window.start,
            "valid_to": self.window.end,
            "validity_precision": self.window.precision,
            "confidence": self.confidence,
            "source_ids": list(self.source_ids),
            "strength": self.strength,
            "extracted_at": self.extracted_at.isoformat() if self.extracted_at else None,
        }


@dataclass
class VersionGroup:
    """Every observation of one subject/predicate pair, newest first."""

    subject: str
    predicate: str
    versions: list[ClaimVersion] = field(default_factory=list)
    #: Pairs of claim ids that genuinely conflict (same period, different value).
    conflicts: list[tuple[str, str]] = field(default_factory=list)

    @property
    def status(self) -> str:
        """``conflicted`` | ``versioned`` | ``single``."""
        if self.conflicts:
            return "conflicted"
        if len({normalize_value(v.value) for v in self.versions}) > 1:
            return "versioned"
        return "single"

    @property
    def latest(self) -> ClaimVersion | None:
        return self.versions[0] if self.versions else None

    @property
    def strongest(self) -> ClaimVersion | None:
        """The version to trust when values disagree: best evidence wins, then recency."""
        if not self.versions:
            return None
        return max(
            self.versions,
            key=lambda v: (v.strength if v.strength is not None else 0.0,
                           v.window.year or 0),
        )

    @property
    def span(self) -> tuple[int | None, int | None]:
        """Oldest and newest year in the group — the visible direction of travel."""
        years = [v.window.year for v in self.versions if v.window.year is not None]
        if not years:
            return (None, None)
        return (min(years), max(years))

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "status": self.status,
            "span": {"from": self.span[0], "to": self.span[1]},
            "conflicts": [list(pair) for pair in self.conflicts],
            "versions": [version.to_dict() for version in self.versions],
        }


def normalize_value(value: str) -> str:
    """Reduce a value to comparable text: no separators, no percent wording."""
    text = (value or "").strip().lower()
    text = _PERCENT_WORDS.sub("", text)
    text = text.replace("%", " ")
    text = _VALUE_NOISE.sub(" ", text)
    return text.strip(" .;")


def _as_number(value: str) -> float | None:
    match = _NUMBER.search(value or "")
    return float(match.group()) if match else None


def values_disagree(left: str, right: str) -> bool:
    """Whether two values are incompatible.

    Absent values never disagree — silence is not a conflict. Numeric pairs are
    compared with a tolerance so rounding is not mistaken for disagreement.
    """
    left_norm = normalize_value(left)
    right_norm = normalize_value(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return False

    left_number = _as_number(left_norm)
    right_number = _as_number(right_norm)
    if left_number is not None and right_number is not None:
        scale = max(abs(left_number), abs(right_number), 1e-9)
        return abs(left_number - right_number) / scale > NUMERIC_EQUALITY_TOLERANCE

    return SequenceMatcher(None, left_norm, right_norm).ratio() < VALUE_SIMILARITY_FLOOR


def build_version_groups(versions: list[ClaimVersion]) -> list[VersionGroup]:
    """Group observations by subject/predicate and classify each group.

    A pair is only a conflict when the values disagree *and* the two claims speak
    about the same period. Everything else is a version — the fact changing over time
    or being restated.
    """
    grouped: dict[tuple[str, str], list[ClaimVersion]] = {}
    for version in versions:
        if not version.subject:
            continue
        grouped.setdefault(version.group_key, []).append(version)

    groups: list[VersionGroup] = []
    for (subject, predicate), members in grouped.items():
        # Newest first, with ties broken by stronger evidence so the "latest" reading
        # is the most defensible one rather than the last row to arrive.
        members.sort(
            key=lambda v: (v.window.year or 0, v.strength or 0.0), reverse=True
        )

        conflicts: list[tuple[str, str]] = []
        for index, left in enumerate(members):
            for right in members[index + 1 :]:
                if not values_disagree(left.value, right.value):
                    continue
                if temporal_relation(left.window, right.window) == "same":
                    conflicts.append((left.claim_id, right.claim_id))

        groups.append(
            VersionGroup(
                subject=subject,
                predicate=predicate,
                versions=members,
                conflicts=conflicts,
            )
        )

    return groups


def versioning_summary(groups: list[VersionGroup]) -> dict[str, int]:
    """Counts for telemetry: how much of the run was versioning rather than conflict."""
    return {
        "groups": len(groups),
        "single": sum(1 for g in groups if g.status == "single"),
        "versioned": sum(1 for g in groups if g.status == "versioned"),
        "conflicted": sum(1 for g in groups if g.status == "conflicted"),
    }
