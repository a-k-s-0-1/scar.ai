"""Long-term memory API routes (V2 2.1).

Cross-session knowledge is only trustworthy if it is inspectable: these routes let the
UI show what the system remembers, why a recalled item scored where it did, and remove
something that should never have been learned. Without them the store would be a black
box that silently changes how later runs behave.
"""

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import ApiKeyAuth, DbSession
from app.api.errors import SessionNotFoundError
from app.api.schemas.memory import (
    MemoryConflictItem,
    MemoryConflictsResponse,
    MemoryItemModel,
    MemoryListResponse,
    MemoryPromoteRequest,
    MemoryPromoteResponse,
    MemoryProvenanceModel,
    MemoryPruneResponse,
    MemorySessionResponse,
    MemoryStatsResponse,
    MemoryVersionModel,
)
from app.database.repository import SessionRepository
from app.services.memory import (
    STATUS_ACTIVE,
    STATUS_CONFLICTING,
    STATUS_NEEDS_VERIFICATION,
    STATUS_SUPERSEDED,
    LongTermMemory,
    memory_kinds,
)
from app.services.memory.promote import promote_session

router = APIRouter(prefix="/api/memory", tags=["Long-Term Memory"])


def _to_model(item: dict) -> MemoryItemModel:
    """Map a memory record (optionally a recalled one) onto the API model."""
    return MemoryItemModel(
        id=item["id"],
        kind=item["kind"],
        key=item["key"],
        text=item["text"],
        payload=item.get("payload") or {},
        importance=item.get("importance", 0.5),
        confidence=item.get("confidence", 0.6),
        hits=item.get("hits", 0),
        embedded=bool(item.get("embedding")),
        embedding_model=item.get("embedding_model"),
        source_session_id=item.get("source_session_id"),
        created_at=item.get("created_at"),
        updated_at=item.get("updated_at"),
        last_used_at=item.get("last_used_at"),
        recall=item.get("recall"),
    )


@router.get(
    "",
    response_model=MemoryListResponse,
    summary="List what the agent remembers across sessions",
)
async def list_memory(
    auth: ApiKeyAuth,
    kind: str | None = Query(None, description="Filter by memory kind"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> MemoryListResponse:
    """Page through stored knowledge, newest-important first."""
    if kind is not None and kind not in memory_kinds():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown memory kind '{kind}'. Known kinds: {memory_kinds()}",
        )

    memory = LongTermMemory()
    items = await memory.list_items(kind=kind, limit=limit, offset=offset)
    return MemoryListResponse(total=len(items), items=[_to_model(i) for i in items])


@router.get(
    "/search",
    response_model=MemoryListResponse,
    summary="Semantic/structured search over remembered knowledge",
)
async def search_memory(
    auth: ApiKeyAuth,
    q: str = Query(..., min_length=1, description="What to search for"),
    kind: str | None = Query(None, description="Restrict to one kind"),
    limit: int = Query(8, ge=1, le=50),
) -> MemoryListResponse:
    """Structured search over the memory store (the same retrieval the loop uses)."""
    memory = LongTermMemory()
    kinds = [kind] if kind else None
    items = await memory.recall(q, kinds=kinds, limit=limit, touch=False)
    return MemoryListResponse(
        total=len(items), items=[_to_model(item.to_dict()) for item in items]
    )


@router.get(
    "/session/{session_id}",
    response_model=MemorySessionResponse,
    summary="What one session contributed to long-term memory",
)
async def memory_for_session(
    session_id: str,
    auth: ApiKeyAuth,
    limit: int = Query(200, ge=1, le=500),
) -> MemorySessionResponse:
    """Every remembered item this run is responsible for, each with its provenance."""
    items = await LongTermMemory().items_for_session(session_id, limit=limit)
    return MemorySessionResponse(
        session_id=session_id, total=len(items), items=items
    )


@router.get(
    "/conflicts",
    response_model=MemoryConflictsResponse,
    summary="Remembered facts that moved, conflict, or need verification",
)
async def memory_conflicts(
    auth: ApiKeyAuth,
    # Named ``status_filter`` so it cannot shadow the ``fastapi.status`` module used
    # below for the error codes.
    status_filter: str | None = Query(
        None,
        alias="status",
        description=(
            "Filter by status: conflicting, superseded, needs_verification, active"
        ),
    ),
    limit: int = Query(100, ge=1, le=500),
) -> MemoryConflictsResponse:
    """The OLD / NEW / STATUS view: every version with its sources and dates.

    A fact that moved is not a contradiction but it is also not the same fact; both
    readings are kept so temporal research can show what changed and when.
    """
    known = {
        STATUS_ACTIVE,
        STATUS_SUPERSEDED,
        STATUS_CONFLICTING,
        STATUS_NEEDS_VERIFICATION,
    }
    if status_filter is not None and status_filter not in known:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unknown memory status '{status_filter}'. "
                f"Known statuses: {sorted(known)}"
            ),
        )

    memory = LongTermMemory()
    items = await memory.versioned_claims(
        statuses=[status_filter] if status_filter else None, limit=limit
    )
    status_counts: dict[str, int] = {}
    for item in items:
        key = str(item.get("status") or "active")
        status_counts[key] = status_counts.get(key, 0) + 1

    return MemoryConflictsResponse(
        total=len(items),
        status_counts=status_counts,
        items=[
            MemoryConflictItem(
                id=item["id"],
                key=item["key"],
                text=item["text"],
                subject=item.get("subject"),
                predicate=item.get("predicate"),
                status=str(item.get("status") or "active"),
                conflicts=int(item.get("conflicts") or 0),
                sources=list(item.get("sources") or []),
                versions=[
                    MemoryVersionModel(**version) for version in item.get("versions", [])
                ],
                importance=float(item.get("importance", 0.5)),
                confidence=float(item.get("confidence", 0.6)),
                provenance=MemoryProvenanceModel(
                    session_id=item.get("source_session_id"),
                    created_at=item.get("created_at"),
                    last_verified_at=item.get("updated_at"),
                    status=str(item.get("status") or "active"),
                    sources=list(item.get("sources") or []),
                ),
            )
            for item in items
        ],
    )


@router.post(
    "/promote",
    response_model=MemoryPromoteResponse,
    summary="Promote a finished session's durable knowledge into memory",
)
async def promote_memory(
    payload: MemoryPromoteRequest,
    auth: ApiKeyAuth,
    db: DbSession,
) -> MemoryPromoteResponse:
    """Re-derive what a session is worth remembering from its stored evidence.

    Useful for runs recorded before memory (or versioning) existed, and idempotent:
    keys are content-derived, so promoting twice updates rather than duplicates.
    """
    if await SessionRepository(db).get_by_id(payload.session_id) is None:
        raise SessionNotFoundError(payload.session_id)

    result = await promote_session(
        payload.session_id,
        db,
        LongTermMemory(),
        max_claims=payload.max_claims,
        max_sources=payload.max_sources,
    )
    return MemoryPromoteResponse(
        session_id=payload.session_id,
        stored=result.get("stored") or {},
        updates=result.get("updates") or {},
        reason=result.get("reason"),
    )


@router.get(
    "/stats",
    response_model=MemoryStatsResponse,
    summary="Memory store size, composition and forgetting policy",
)
async def memory_stats(auth: ApiKeyAuth) -> MemoryStatsResponse:
    """Report how much is remembered, how much carries a vector, and how fast it decays."""
    stats = await LongTermMemory().stats()
    return MemoryStatsResponse(**stats)


@router.get(
    "/recall",
    response_model=MemoryListResponse,
    summary="Recall knowledge relevant to a question",
)
async def recall_memory(
    auth: ApiKeyAuth,
    q: str = Query(..., min_length=1, description="Question or topic to recall for"),
    kind: str | None = Query(None, description="Restrict recall to one kind"),
    limit: int = Query(8, ge=1, le=50),
) -> MemoryListResponse:
    """Runs the same retrieval the research loop uses, so recall can be inspected.

    Returns the score breakdown per item — lexical, semantic and decay — because a
    recall that cannot be explained cannot be tuned.
    """
    memory = LongTermMemory()
    kinds = [kind] if kind else None
    items = await memory.recall(q, kinds=kinds, limit=limit, touch=False)
    return MemoryListResponse(
        total=len(items), items=[_to_model(item.to_dict()) for item in items]
    )


@router.post(
    "/prune",
    response_model=MemoryPruneResponse,
    summary="Forget decayed knowledge and enforce the size cap",
)
async def prune_memory(auth: ApiKeyAuth) -> MemoryPruneResponse:
    """Run the forgetting policy on demand instead of waiting for the next run."""
    removed = await LongTermMemory().decay_and_prune()
    return MemoryPruneResponse(**removed)


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Forget one remembered item",
)
async def forget_memory_item(item_id: str, auth: ApiKeyAuth) -> None:
    """Delete a single memory item — the user's override of what was learned."""
    deleted = await LongTermMemory().forget(item_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory item {item_id} not found.",
        )
