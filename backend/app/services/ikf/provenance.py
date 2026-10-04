"""Provenance — every claim and edge carries where it came from and how independently.

An edge that says "there is a relationship" is not actionable. An edge that says
"four sources support this, two of them independent domains, extracted in iteration 3"
is. Provenance is what turns the graph from a picture into an argument, and it is a
prerequisite for evidence strength: three syndicated copies of one wire story are one
source, not three, and only the *domain* count knows the difference.

The module is DB-free; the service layer maps ORM rows onto ``SourceRef``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

SUPPORT_TYPES = ("supports", "refutes", "neutral")


@dataclass(frozen=True)
class SourceRef:
    """A claim's link to one source, flattened for scoring."""

    source_id: str
    url: str = ""
    source_type: str = "unknown"
    credibility: float = 0.5
    published_at: datetime | None = None
    support_type: str = "supports"
    link_confidence: float = 0.8


def domain_of(url: str) -> str:
    """Registrable-ish host for independence counting ("www." is not a publisher)."""
    if not url:
        return ""
    host = urlparse(url if "//" in url else f"//{url}").netloc.lower()
    if not host:
        return ""
    host = host.removeprefix("www.")
    return host


@dataclass
class Provenance:
    """Where a claim or edge came from, and how independent the support is."""

    source_ids: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    supports: int = 0
    refutes: int = 0
    neutral: int = 0
    extracted_at: datetime | None = None
    #: Support type per entry of ``source_ids``, so the serialised payload can say
    #: *which* source supported rather than only how many did.
    support_types: list[str] = field(default_factory=list, repr=False)

    @property
    def independent_sources(self) -> int:
        """Distinct publishers behind the evidence.

        Links whose URL yielded no host still count individually — they are distinct
        stored sources, and dropping them would understate support.
        """
        named = {domain for domain in self.domains if domain}
        unnamed = sum(1 for domain in self.domains if not domain)
        return len(named) + unnamed

    @property
    def total_sources(self) -> int:
        return len(self.source_ids)

    def to_dict(self) -> dict:
        """Serialise for storage.

        Per-source detail is kept rather than only aggregates, because an edge
        accumulates support across iterations: merging two payloads exactly requires
        knowing *which* source supported and refuted, not just how many did.
        """
        domain_by_source = {
            source_id: domain
            for source_id, domain in zip(self.source_ids, self.domains, strict=False)
        }
        return {
            "source_ids": list(self.source_ids),
            "domain_by_source": domain_by_source,
            "supports_ids": self._ids_for("supports"),
            "refutes_ids": self._ids_for("refutes"),
            "neutral_ids": self._ids_for("neutral"),
            "independent_sources": self.independent_sources,
            "total_sources": self.total_sources,
            "supports": self.supports,
            "refutes": self.refutes,
            "neutral": self.neutral,
            "extracted_at": self.extracted_at.isoformat()
            if self.extracted_at
            else None,
        }

    def _ids_for(self, support_type: str) -> list[str]:
        return [
            source_id
            for source_id, kind in zip(
                self.source_ids, self.support_types, strict=False
            )
            if kind == support_type
        ]


def build_provenance(
    refs: list[SourceRef], extracted_at: datetime | None = None
) -> Provenance:
    """Fold a claim's source links into one provenance record.

    Duplicate links to the same source are collapsed: the same document cannot be
    evidence twice.
    """
    seen: dict[str, SourceRef] = {}
    for ref in refs:
        seen.setdefault(ref.source_id, ref)

    supports = sum(
        1 for ref in seen.values() if ref.support_type == "supports"
    )
    refutes = sum(1 for ref in seen.values() if ref.support_type == "refutes")
    neutral = len(seen) - supports - refutes

    return Provenance(
        source_ids=list(seen.keys()),
        domains=[domain_of(ref.url) for ref in seen.values()],
        supports=supports,
        refutes=refutes,
        neutral=neutral,
        extracted_at=extracted_at,
        support_types=[ref.support_type for ref in seen.values()],
    )


def edge_provenance(
    refs: list[SourceRef],
    claim_ids: list[str],
    extracted_at: datetime | None = None,
) -> dict:
    """Provenance payload for a knowledge edge, ready to serialize onto the graph.

    Keeps the contributing claim ids alongside the source roll-up so a reader can walk
    an edge back to the exact assertions that produced it.
    """
    provenance = build_provenance(refs, extracted_at=extracted_at)
    payload = provenance.to_dict()
    payload["claim_ids"] = list(dict.fromkeys(claim_ids))
    payload["support_weight"] = round(
        (provenance.supports + 0.5 * provenance.neutral)
        / max(1, provenance.total_sources),
        4,
    )
    return payload


def _recompute(payload: dict) -> dict:
    """Recompute every derived field from the unioned per-source lists."""
    source_ids = list(payload["source_ids"])
    domain_by_source = dict(payload["domain_by_source"])
    supports_ids = list(payload["supports_ids"])
    refutes_ids = list(payload["refutes_ids"])
    neutral_ids = list(payload["neutral_ids"])

    payload["supports"] = len(supports_ids)
    payload["refutes"] = len(refutes_ids)
    payload["neutral"] = len(neutral_ids)
    payload["total_sources"] = len(source_ids)

    named = {domain for domain in domain_by_source.values() if domain}
    unnamed = sum(1 for sid in source_ids if not domain_by_source.get(sid))
    payload["independent_sources"] = len(named) + unnamed
    payload["support_weight"] = round(
        (payload["supports"] + 0.5 * payload["neutral"])
        / max(1, payload["total_sources"]),
        4,
    )
    return payload


def merge_provenance(existing: dict | None, incoming: dict) -> dict:
    """Fold a new provenance payload into the one already stored for an edge.

    The same relationship is asserted by many claims across iterations, and a second
    assertion must widen the evidence rather than overwrite it. Merging on the
    per-source lists keeps the counts exact: one source cannot be counted twice, and
    a source that both supports and refutes is recorded as refuting, which is the
    safer reading.
    """
    if not existing:
        return _recompute(dict(incoming))

    merged = {
        "source_ids": [],
        "domain_by_source": {},
        "supports_ids": [],
        "refutes_ids": [],
        "neutral_ids": [],
        "claim_ids": [],
        "extracted_at": incoming.get("extracted_at") or existing.get("extracted_at"),
    }

    for payload in (existing, incoming):
        for source_id in payload.get("source_ids", []):
            if source_id not in merged["source_ids"]:
                merged["source_ids"].append(source_id)
        merged["domain_by_source"].update(payload.get("domain_by_source", {}))
        for key in ("supports_ids", "refutes_ids", "neutral_ids", "claim_ids"):
            for value in payload.get(key, []):
                if value not in merged[key]:
                    merged[key].append(value)

    # A source that refutes anywhere must not also be counted as supporting.
    refutes = set(merged["refutes_ids"])
    merged["supports_ids"] = [
        sid for sid in merged["supports_ids"] if sid not in refutes
    ]
    merged["neutral_ids"] = [
        sid
        for sid in merged["neutral_ids"]
        if sid not in refutes and sid not in set(merged["supports_ids"])
    ]

    return _recompute(merged)
