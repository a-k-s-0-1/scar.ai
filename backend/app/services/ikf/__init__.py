"""IKF 2.0 — knowledge intelligence layered on top of the V1 fusion pipeline.

The sub-modules are pure and DB-free so the maths is testable in isolation:

* ``entity_resolution``  — one node per real thing, not one per spelling
* ``temporal``           — when a claim was true, and how much that still matters
* ``claim_versioning``   — the same fact moving in time is not a contradiction
* ``provenance``         — where a claim or edge came from, and how independently
* ``evidence``           — a real strength score in place of a flat confidence label
* ``service``            — the only module here that knows about the database
"""

from app.services.ikf.claim_versioning import (
    ClaimVersion,
    VersionGroup,
    build_version_groups,
    values_disagree,
    versioning_summary,
)
from app.services.ikf.entity_resolution import (
    EntityResolver,
    normalize_entity,
    should_merge,
    similarity,
)
from app.services.ikf.evidence import (
    EvidenceInput,
    EvidenceScore,
    aggregate_evidence,
    band_for,
    evidence_summary,
    extraction_confidence,
    score_claim,
)
from app.services.ikf.provenance import (
    Provenance,
    SourceRef,
    build_provenance,
    domain_of,
    edge_provenance,
    merge_provenance,
)
from app.services.ikf.service import (
    KnowledgeIndex,
    build_claim_versions,
    build_evidence_inputs,
    build_knowledge_index,
    claim_source_refs,
)
from app.services.ikf.temporal import (
    ValidityWindow,
    extract_validity_window,
    recency_score,
    temporal_relation,
)

__all__ = [
    "ClaimVersion",
    "EntityResolver",
    "EvidenceInput",
    "EvidenceScore",
    "KnowledgeIndex",
    "Provenance",
    "SourceRef",
    "ValidityWindow",
    "VersionGroup",
    "aggregate_evidence",
    "band_for",
    "build_claim_versions",
    "build_evidence_inputs",
    "build_knowledge_index",
    "build_provenance",
    "build_version_groups",
    "claim_source_refs",
    "domain_of",
    "edge_provenance",
    "evidence_summary",
    "extract_validity_window",
    "extraction_confidence",
    "merge_provenance",
    "normalize_entity",
    "recency_score",
    "score_claim",
    "should_merge",
    "similarity",
    "temporal_relation",
    "values_disagree",
    "versioning_summary",
]
