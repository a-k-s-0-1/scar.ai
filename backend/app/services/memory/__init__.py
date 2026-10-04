"""Long-term memory (V2 2.1) — knowledge that outlives a research run.

* ``store``      — kinds, records, and the pure importance/decay/forgetting policy
* ``embeddings`` — pluggable embedding provider (Gemini, with a never-raising path)
* ``retrieval``  — lexical + semantic + decay scoring and ranking
* ``service``    — ``LongTermMemory``: the only module here that touches the database
"""

from app.services.memory.embeddings import (
    EmbeddingProvider,
    GeminiEmbeddings,
    NullEmbeddings,
    cosine_similarity,
    get_embedding_provider,
)
from app.services.memory.retrieval import (
    ScoredMemory,
    lexical_score,
    rank_records,
    score_record,
    tokenize,
)
from app.services.memory.service import (
    EMBEDDED_KINDS,
    MAX_EMBEDDINGS_PER_BATCH,
    RECALL_CANDIDATE_LIMIT,
    LongTermMemory,
    MemoryWrite,
    get_session_factory,
    memory_kinds,
    set_session_factory,
)
from app.services.memory.store import (
    BASE_IMPORTANCE,
    MemoryKind,
    MemoryRecord,
    decay_weight,
    importance_for,
    normalize_key,
    reuse_boost,
    should_forget,
)
from app.services.memory.versions import (
    GROUP_STATUSES,
    STATUS_ACTIVE,
    STATUS_CONFLICTING,
    STATUS_NEEDS_VERIFICATION,
    STATUS_SUPERSEDED,
    ClaimVersionRecord,
    MemoryUpdateSummary,
    claim_version_from_ikf,
    conflict_report,
    group_status,
    merge_versions,
    version_statuses,
)

__all__ = [
    "BASE_IMPORTANCE",
    "EMBEDDED_KINDS",
    "GROUP_STATUSES",
    "MAX_EMBEDDINGS_PER_BATCH",
    "RECALL_CANDIDATE_LIMIT",
    "STATUS_ACTIVE",
    "STATUS_CONFLICTING",
    "STATUS_NEEDS_VERIFICATION",
    "STATUS_SUPERSEDED",
    "ClaimVersionRecord",
    "EmbeddingProvider",
    "GeminiEmbeddings",
    "LongTermMemory",
    "MemoryKind",
    "MemoryRecord",
    "MemoryUpdateSummary",
    "MemoryWrite",
    "NullEmbeddings",
    "ScoredMemory",
    "claim_version_from_ikf",
    "conflict_report",
    "cosine_similarity",
    "decay_weight",
    "get_embedding_provider",
    "get_session_factory",
    "group_status",
    "importance_for",
    "lexical_score",
    "memory_kinds",
    "merge_versions",
    "normalize_key",
    "rank_records",
    "reuse_boost",
    "score_record",
    "set_session_factory",
    "should_forget",
    "tokenize",
    "version_statuses",
]
