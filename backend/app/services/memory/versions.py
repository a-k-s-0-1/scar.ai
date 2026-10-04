"""Memory update rules (V2 2.12) — supersede, conflict, or ask for verification.

New research that contradicts something already remembered must not silently overwrite
it. A memory claim therefore carries *versions*: every observation of the same
subject/predicate pair, with the value, the period it speaks about, where it came from
and when it was recorded. This module decides what each version's status is:

``active``
    The current reading of the fact — the newest version, or the only one.
``superseded``
    An earlier version of a fact that has since moved (``2025: 4 %`` → ``2026: 9 %``).
``conflicting``
    Two versions that describe the same period with incompatible values. This is the
    case that must be surfaced, not resolved by whoever wrote last.
``needs_verification``
    Versions whose period is unknown cannot be ordered, so no supersede/conflict
    judgement is safe; they are flagged for verification instead of guessed at.

The rules are pure and reuse the IKF layer's disagreement test, so a claim is never
"conflicting" in memory while the knowledge graph calls it a versioned fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.services.ikf.claim_versioning import values_disagree

STATUS_ACTIVE = "active"
STATUS_SUPERSEDED = "superseded"
STATUS_CONFLICTING = "conflicting"
STATUS_NEEDS_VERIFICATION = "needs_verification"

#: Versions kept per fact. Older observations are dropped from the *tail* only after
#: sorting newest-first, so what survives is the current reading and its recent past.
MAX_VERSIONS = 8

GROUP_STATUSES = (
    STATUS_ACTIVE,
    STATUS_SUPERSEDED,
    STATUS_CONFLICTING,
    STATUS_NEEDS_VERIFICATION,
)


@dataclass(frozen=True)
class ClaimVersionRecord:
    """One observation of a fact, with provenance."""

    value: str
    #: The full sentence the claim was extracted from, kept so a recalled memory reads
    #: like research rather than like a database row (and so embeddings embed prose).
    text: str = ""
    valid_from: int | None = None
    valid_to: int | None = None
    precision: str = "unknown"
    session_id: str | None = None
    claim_id: str | None = None
    sources: tuple[str, ...] = ()
    confidence: float = 0.6
    recorded_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "text": self.text,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "precision": self.precision,
            "session_id": self.session_id,
            "claim_id": self.claim_id,
            "sources": list(self.sources),
            "confidence": round(float(self.confidence), 4),
            "recorded_at": self.recorded_at or _now_iso(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ClaimVersionRecord:
        return cls(
            value=str(payload.get("value", "")),
            text=str(payload.get("text", "") or ""),
            valid_from=payload.get("valid_from"),
            valid_to=payload.get("valid_to"),
            precision=str(payload.get("precision", "unknown")),
            session_id=payload.get("session_id"),
            claim_id=payload.get("claim_id"),
            sources=tuple(payload.get("sources") or ()),
            confidence=float(payload.get("confidence", 0.6) or 0.6),
            recorded_at=payload.get("recorded_at"),
        )

    @property
    def sort_year(self) -> int:
        """The most specific year this version speaks about, 0 when unknown."""
        return int(self.valid_to or self.valid_from or 0)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _overlaps(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Whether two stored versions claim the same period.

    An unknown period overlaps nothing *and* nothing overlaps it: without a date there
    is no way to tell a moved fact from a disagreement, which is exactly why such
    versions end up needing verification rather than a verdict.
    """
    left_start = left.get("valid_from") or left.get("valid_to")
    left_end = left.get("valid_to") or left.get("valid_from")
    right_start = right.get("valid_from") or right.get("valid_to")
    right_end = right.get("valid_to") or right.get("valid_from")
    if left_start is None or right_start is None:
        return False
    return int(left_start) <= int(right_end) and int(right_start) <= int(left_end)


def _identity(version: dict[str, Any]) -> tuple[Any, ...]:
    """What makes two version entries the same observation (so re-learning updates)."""
    return (
        str(version.get("value", "")).strip().lower(),
        version.get("valid_from"),
        version.get("valid_to"),
        version.get("session_id"),
    )


def merge_versions(
    existing: list[dict[str, Any]] | None,
    incoming: ClaimVersionRecord,
    *,
    max_versions: int = MAX_VERSIONS,
) -> list[dict[str, Any]]:
    """Merge one observation into the stored list, newest first.

    Re-learning the same fact from the same run updates that entry instead of adding a
    duplicate; a *newer* observation with the same period and value replaces the older
    one's provenance, because the newer evidence is the one worth citing.
    """
    merged: list[dict[str, Any]] = [dict(item) for item in (existing or [])]
    candidate = incoming.to_dict()

    for index, item in enumerate(merged):
        if _identity(item) == _identity(candidate):
            merged[index] = {**item, **candidate}
            break
    else:
        merged.append(candidate)

    merged.sort(
        key=lambda item: (
            int(item.get("valid_to") or item.get("valid_from") or 0),
            float(item.get("confidence") or 0.0),
        ),
        reverse=True,
    )
    return merged[: max(1, max_versions)]


def version_statuses(versions: list[dict[str, Any]]) -> list[str]:
    """Status of each version, aligned with the input order (newest first)."""
    if not versions:
        return []

    statuses = [STATUS_ACTIVE] * len(versions)

    # A genuine disagreement is the loudest signal, so it is decided first.
    for left in range(len(versions)):
        for right in range(left + 1, len(versions)):
            if not _overlaps(versions[left], versions[right]):
                continue
            if values_disagree(
                str(versions[left].get("value", "")),
                str(versions[right].get("value", "")),
            ):
                statuses[left] = STATUS_CONFLICTING
                statuses[right] = STATUS_CONFLICTING
            elif str(versions[left].get("value", "")) == str(
                versions[right].get("value", "")
            ):
                # Same period, same value: one fact restated. The older entry is
                # history, not a second claim.
                statuses[right] = STATUS_SUPERSEDED

    for index, version in enumerate(versions):
        if statuses[index] == STATUS_CONFLICTING:
            continue
        has_period = bool(version.get("valid_from") or version.get("valid_to"))
        if not has_period and len(versions) > 1:
            # Cannot be ordered against the others without a date.
            statuses[index] = STATUS_NEEDS_VERIFICATION
        elif index > 0 and statuses[index] == STATUS_ACTIVE:
            # Older entries with a known period are superseded by the newest reading.
            statuses[index] = STATUS_SUPERSEDED

    return statuses


def group_status(versions: list[dict[str, Any]]) -> str:
    """One status for the remembered fact, from the spec's vocabulary."""
    statuses = version_statuses(versions)
    if STATUS_CONFLICTING in statuses:
        return STATUS_CONFLICTING
    if STATUS_NEEDS_VERIFICATION in statuses:
        return STATUS_NEEDS_VERIFICATION
    if STATUS_SUPERSEDED in statuses:
        return STATUS_SUPERSEDED
    return STATUS_ACTIVE


def conflict_report(versions: list[dict[str, Any]]) -> dict[str, Any]:
    """The full OLD/NEW/STATUS view the memory panel renders."""
    statuses = version_statuses(versions)
    enriched = [
        {**version, "status": statuses[index]}
        for index, version in enumerate(versions)
    ]
    conflicts: list[dict[str, Any]] = []
    for left in range(len(enriched)):
        for right in range(left + 1, len(enriched)):
            if (
                enriched[left]["status"] == STATUS_CONFLICTING
                and enriched[right]["status"] == STATUS_CONFLICTING
                and _overlaps(enriched[left], enriched[right])
                and values_disagree(
                    str(enriched[left].get("value", "")),
                    str(enriched[right].get("value", "")),
                )
            ):
                conflicts.append(
                    {
                        "old": enriched[right],
                        "new": enriched[left],
                        "reason": "same period, incompatible values",
                    }
                )

    current = next(
        (item for item in enriched if item["status"] == STATUS_ACTIVE), None
    )
    return {
        "status": group_status(versions),
        "versions": enriched,
        "conflicts": conflicts,
        "current": current,
        "superseded": [item for item in enriched if item["status"] == STATUS_SUPERSEDED],
        "needs_verification": [
            item
            for item in enriched
            if item["status"] == STATUS_NEEDS_VERIFICATION
        ],
    }


def claim_version_from_ikf(
    version: Any,
    *,
    session_id: str,
    sources: list[str] | None = None,
) -> ClaimVersionRecord:
    """Adapt an IKF ``ClaimVersion`` (which has a validity window) into a memory record."""
    window = getattr(version, "window", None)
    return ClaimVersionRecord(
        value=str(getattr(version, "value", "") or "").strip(),
        text=str(getattr(version, "text", "") or "").strip(),
        valid_from=getattr(window, "start", None),
        valid_to=getattr(window, "end", None),
        precision=str(getattr(window, "precision", "unknown") or "unknown"),
        session_id=session_id,
        claim_id=getattr(version, "claim_id", None),
        sources=tuple(sources or ()),
        confidence=(
            float(version.strength)
            if getattr(version, "strength", None) is not None
            else {"high": 0.9, "medium": 0.6, "low": 0.35}.get(
                str(getattr(version, "confidence", "medium")).lower(), 0.6
            )
        ),
        recorded_at=(
            version.extracted_at.isoformat()
            if getattr(version, "extracted_at", None)
            else None
        ),
    )


@dataclass
class MemoryUpdateSummary:
    """What one session changed about remembered facts."""

    new_facts: int = 0
    updated_facts: int = 0
    superseded: int = 0
    conflicting: int = 0
    needs_verification: int = 0
    statuses: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, int]:
        return {
            "new_facts": self.new_facts,
            "updated_facts": self.updated_facts,
            "superseded": self.superseded,
            "conflicting": self.conflicting,
            "needs_verification": self.needs_verification,
            **{f"status_{key}": value for key, value in sorted(self.statuses.items())},
        }
