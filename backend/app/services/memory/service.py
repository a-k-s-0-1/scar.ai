"""Long-term memory — the knowledge that outlives a research run (V2 2.1).

Every V1/V2 mechanism so far forgets everything the moment a session ends: the search
memory, the facet coverage, the resolved entities, the report. This service is where
that knowledge is persisted, recalled, and eventually forgotten.

Design decisions worth stating:

* **Writes never break a run.** Saving memory happens after the work is done and is
  wrapped so a failure is logged, not raised — a memory bug must not cost the user a
  completed investigation.
* **Only some kinds get embeddings.** Embedding is a paid remote call, so it is spent on
  knowledge worth semantic recall (conclusions, claims, strategies, entities, past
  questions). Failed queries and source URLs are matched lexically and need no vector.
* **Recall is bounded twice** — by a capped candidate set and by a per-call limit — so
  retrieval cost does not grow with the size of the memory.
* **Forgetting is part of the design**, not a cleanup afterthought: weight decays with
  idleness, rises with reuse, and a cap evicts the lowest weight so the store cannot
  grow forever in one direction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.database.repository import MemoryRepository
from app.services.memory.embeddings import EmbeddingProvider, get_embedding_provider
from app.services.memory.retrieval import ScoredMemory, rank_records
from app.services.memory.store import (
    MemoryKind,
    MemoryRecord,
    decay_weight,
    importance_for,
    normalize_key,
    should_forget,
)
from app.services.memory.versions import (
    STATUS_CONFLICTING,
    STATUS_NEEDS_VERIFICATION,
    STATUS_SUPERSEDED,
    ClaimVersionRecord,
    MemoryUpdateSummary,
    conflict_report,
    merge_versions,
)
from app.utils.logger import logger

#: Kinds worth spending an embedding call on.
EMBEDDED_KINDS = frozenset(
    {
        MemoryKind.CONCLUSION.value,
        MemoryKind.CLAIM.value,
        MemoryKind.STRATEGY.value,
        MemoryKind.ENTITY.value,
        MemoryKind.DOMAIN.value,
        MemoryKind.RESEARCH_HISTORY.value,
        MemoryKind.RESOLVED_CONTRADICTION.value,
    }
)

#: Ceiling on embedding calls per batch write, so persisting a large run cannot turn
#: into dozens of provider calls after the user is already waiting for the report.
MAX_EMBEDDINGS_PER_BATCH = 25

#: Candidate pool for ranking, and how much of the store a single recall may touch.
RECALL_CANDIDATE_LIMIT = 400


@dataclass
class MemoryWrite:
    """One item to persist."""

    kind: str
    text: str
    key: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    importance: float | None = None

    def resolved_key(self) -> str:
        return self.key or normalize_key(self.kind, self.text)


# ─── session factory indirection (matches event_recorder's pattern) ──────────

_session_factory: Any = None


def set_session_factory(factory: Any) -> None:
    """Point memory writes at a specific session maker (the app, or a test database)."""
    global _session_factory
    _session_factory = factory


def get_session_factory() -> Any:
    """Resolve the session maker lazily so importing this module opens no database."""
    global _session_factory
    if _session_factory is None:
        from app.database.session import async_session_maker

        _session_factory = async_session_maker
    return _session_factory


def _to_record(item: Any) -> MemoryRecord:
    """Map an ORM row onto the pure record used for scoring."""
    return MemoryRecord(
        id=item.id,
        kind=item.kind,
        key=item.key,
        text=item.text,
        payload=item.payload or {},
        importance=item.importance,
        confidence=item.confidence,
        hits=item.hits,
        embedding=item.embedding,
        embedding_model=item.embedding_model,
        source_session_id=item.source_session_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
        last_used_at=item.last_used_at,
    )


class LongTermMemory:
    """Persist, recall and forget durable knowledge.

    Each method opens its own short-lived session, because callers are the research
    loop, the API and the scheduler — none of which should have to hold a transaction
    open across a network call to write a note.
    """

    def __init__(
        self,
        provider: EmbeddingProvider | None = None,
        settings: Any = None,
    ) -> None:
        # Copied rather than held: this service's explicit settings are mutated (tests,
        # and any future per-run override), and mutating the process-wide cached
        # Settings object would leak those changes into every other caller.
        source = settings or get_settings()
        self.settings = source.model_copy() if hasattr(source, "model_copy") else source
        self.provider = provider or get_embedding_provider(self.settings)

    @property
    def enabled(self) -> bool:
        return bool(self.settings.MEMORY_ENABLED)

    # ─── writes ──────────────────────────────────────────────────────────────
    async def remember(
        self,
        kind: str,
        text: str,
        *,
        key: str | None = None,
        payload: dict[str, Any] | None = None,
        confidence: float | None = None,
        importance: float | None = None,
        session_id: str | None = None,
    ) -> MemoryRecord | None:
        """Persist one item (or refresh the one already stored under its key)."""
        writes = [
            MemoryWrite(
                kind=kind,
                text=text,
                key=key,
                payload=payload or {},
                confidence=confidence,
                importance=importance,
            )
        ]
        stored = await self.remember_many(writes, session_id=session_id)
        return stored[0] if stored else None

    async def remember_many(
        self, writes: list[MemoryWrite], session_id: str | None = None
    ) -> list[MemoryRecord]:
        """Persist a batch in one transaction, embedding the kinds worth embedding."""
        if not self.enabled or not writes:
            return []

        embeddings: dict[int, tuple[list[float], str]] = {}
        if self.provider.name != "none":
            spent = 0
            for index, write in enumerate(writes):
                if write.kind not in EMBEDDED_KINDS or spent >= MAX_EMBEDDINGS_PER_BATCH:
                    continue
                vector = await self.provider.embed(write.text)
                if vector:
                    embeddings[index] = (vector, self.provider.name)
                    spent += 1

        stored: list[MemoryRecord] = []
        try:
            async with get_session_factory()() as db:
                repo = MemoryRepository(db)
                for index, write in enumerate(writes):
                    vector, model = embeddings.get(index, (None, None))
                    importance = (
                        write.importance
                        if write.importance is not None
                        else importance_for(write.kind, write.confidence)
                    )
                    item = await repo.upsert(
                        kind=write.kind,
                        key=write.resolved_key(),
                        text=write.text,
                        payload=write.payload,
                        importance=importance,
                        confidence=write.confidence if write.confidence is not None else 0.6,
                        embedding=vector,
                        embedding_model=model,
                        source_session_id=session_id,
                    )
                    stored.append(_to_record(item))
                await db.commit()
        except Exception as exc:  # noqa: BLE001 — memory must never break a run
            logger.warning(f"Memory write failed ({type(exc).__name__}: {exc}).")
            return []

        return stored

    # ─── recall ──────────────────────────────────────────────────────────────
    async def recall(
        self,
        query: str,
        kinds: list[str] | None = None,
        limit: int | None = None,
        touch: bool = True,
    ) -> list[ScoredMemory]:
        """Return the most relevant stored knowledge for a query."""
        if not self.enabled or not query.strip():
            return []

        recall_limit = limit or self.settings.MEMORY_RECALL_LIMIT
        query_vector = await self.provider.embed(query)

        async with get_session_factory()() as db:
            repo = MemoryRepository(db)
            candidates = [
                _to_record(item)
                for item in await repo.candidates(
                    kinds=kinds, limit=RECALL_CANDIDATE_LIMIT
                )
            ]
            ranked = rank_records(
                candidates,
                query,
                query_vector=query_vector,
                limit=recall_limit,
                half_life_days=self.settings.MEMORY_HALF_LIFE_DAYS,
            )
            if touch and ranked:
                # Recalling something and not recording it would let well-used
                # knowledge decay exactly like knowledge nobody has ever needed.
                await repo.touch([item.record.id for item in ranked])
            await db.commit()

        return ranked

    async def recall_texts(
        self, query: str, kinds: list[str] | None = None, limit: int | None = None
    ) -> list[str]:
        """Recall just the text, for callers that only need prompt material."""
        return [item.record.text for item in await self.recall(query, kinds, limit)]

    # ─── domain-specific helpers ─────────────────────────────────────────────
    async def aliases(self, limit: int = 200) -> dict[str, list[str]]:
        """Entity alias table for seeding the resolver, learned from earlier runs.

        This is the highest-value carry-over: an acronym like "IBM" cannot be inferred
        from any similarity measure, so it has to be remembered.
        """
        if not self.enabled:
            return {}

        async with get_session_factory()() as db:
            repo = MemoryRepository(db)
            items = await repo.list_items(kind=MemoryKind.ENTITY.value, limit=limit)

        table: dict[str, list[str]] = {}
        for item in items:
            aliases = (item.payload or {}).get("aliases") or []
            if aliases:
                table[item.text] = [str(alias) for alias in aliases]
        return table

    async def avoided_queries(self, limit: int = 100) -> set[str]:
        """Queries that already came back empty in an *earlier* session.

        Per-run `SearchMemory` cannot know these; remembering them is the difference
        between a dead end costing one run and costing every run.
        """
        if not self.enabled:
            return set()

        async with get_session_factory()() as db:
            repo = MemoryRepository(db)
            items = await repo.list_items(
                kind=MemoryKind.FAILED_QUERY.value, limit=limit
            )
        return {item.key for item in items}

    async def remember_session(
        self,
        *,
        session_id: str,
        question: str,
        summary: str = "",
        stop_reason: str | None = None,
        stats: dict[str, Any] | None = None,
    ) -> None:
        """Record that this question was asked, and how the run went."""
        await self.remember(
            MemoryKind.RESEARCH_HISTORY.value,
            question,
            payload={
                "summary": summary[:600],
                "stop_reason": stop_reason or "",
                "stats": stats or {},
            },
            session_id=session_id,
        )

    async def remember_outcome(
        self,
        *,
        session_id: str,
        question: str,
        summary: str = "",
        stop_reason: str | None = None,
        stats: dict[str, Any] | None = None,
        claims: list[tuple[str, float]] | None = None,
        conclusions: list[str] | None = None,
        entities: dict[str, list[str]] | None = None,
        sources: list[tuple[str, str, float]] | None = None,
        strategies: list[tuple[str, str, float]] | None = None,
        failed_queries: list[str] | None = None,
        resolved: list[str] | None = None,
        domain: str | None = None,
        constraints: dict[str, Any] | None = None,
        max_claims: int = 40,
        max_sources: int = 20,
    ) -> dict[str, int]:
        """Persist everything one finished run should leave behind.

        Takes plain data rather than ORM rows so the mapping from a run to its memory
        is testable on its own, and so the caller cannot accidentally hand over a
        detached instance.

        Per-kind caps matter: a deep run can produce well over a hundred claims, and
        “all of them" is how a memory store becomes a second, worse copy of the
        database. Callers pass collections already ordered best-first (claims by
        evidence strength, sources by credibility) and the tail is dropped.
        """
        if not self.enabled:
            return {}

        writes: list[MemoryWrite] = [
            MemoryWrite(
                kind=MemoryKind.RESEARCH_HISTORY.value,
                text=question,
                payload={
                    "summary": (summary or "")[:600],
                    "stop_reason": stop_reason or "",
                    "stats": stats or {},
                },
            )
        ]

        for text, strength in (claims or [])[:max_claims]:
            if text.strip():
                writes.append(
                    MemoryWrite(
                        kind=MemoryKind.CLAIM.value,
                        text=text,
                        confidence=strength,
                    )
                )

        for text in conclusions or []:
            if text.strip():
                writes.append(MemoryWrite(kind=MemoryKind.CONCLUSION.value, text=text))

        for canonical, aliases in (entities or {}).items():
            if aliases:
                writes.append(
                    MemoryWrite(
                        kind=MemoryKind.ENTITY.value,
                        text=canonical,
                        payload={"aliases": aliases},
                    )
                )

        for url, title, credibility in (sources or [])[:max_sources]:
            writes.append(
                MemoryWrite(
                    kind=MemoryKind.SOURCE.value,
                    text=url,
                    payload={"title": title},
                    confidence=credibility,
                )
            )

        for query, facet, value in strategies or []:
            writes.append(
                MemoryWrite(
                    kind=MemoryKind.SUCCESSFUL_QUERY.value,
                    text=query,
                    payload={"facet": facet, "sources_found": value},
                )
            )

        for query in failed_queries or []:
            writes.append(
                MemoryWrite(
                    kind=MemoryKind.FAILED_QUERY.value,
                    text=query,
                    payload={"session_id": session_id},
                )
            )

        for description in resolved or []:
            writes.append(
                MemoryWrite(
                    kind=MemoryKind.RESOLVED_CONTRADICTION.value,
                    text=description,
                )
            )

        if domain:
            writes.append(
                MemoryWrite(
                    kind=MemoryKind.DOMAIN.value,
                    text=domain,
                    payload={"stats": stats or {}},
                )
            )

        if constraints:
            # One profile per shape of research request, so "the user tends to ask for
            # >=10 sources over a 5 minute budget" is learnable without storing a row
            # per session.
            signature = "|".join(
                str(constraints.get(field, ""))
                for field in ("depth", "min_sources_required", "max_research_time_minutes")
            )
            writes.append(
                MemoryWrite(
                    kind=MemoryKind.CONSTRAINT.value,
                    text=signature,
                    key=f"profile:{signature}",
                    payload=dict(constraints),
                )
            )

        stored = await self.remember_many(writes, session_id=session_id)
        counts: dict[str, int] = {}
        for record in stored:
            counts[record.kind] = counts.get(record.kind, 0) + 1
        logger.info(
            f"Memory after {session_id}: " + ", ".join(
                f"{kind}={total}" for kind, total in sorted(counts.items())
            )
            if counts
            else f"Memory after {session_id}: nothing stored."
        )
        return counts

    # ─── versioned claims and conflicts (V2 2.12) ────────────────────────────
    async def remember_claim_versions(
        self,
        groups: list[dict[str, Any]],
        *,
        session_id: str,
        max_groups: int = 25,
    ) -> MemoryUpdateSummary:
        """Store the facts this run saw move or contradict something already known.

        Only multi-observation facts reach this path: a fact observed once is a claim,
        and blindly versioning every claim would turn memory into a second copy of the
        database. A group is merged into whatever is already remembered under the same
        subject/predicate, so a contradiction found in March is still visible as a
        contradiction in June — with both readings, both sources and both dates.
        """
        summary = MemoryUpdateSummary()
        if not self.enabled or not groups:
            return summary

        try:
            async with get_session_factory()() as db:
                repo = MemoryRepository(db)
                for group in groups[:max_groups]:
                    subject = str(group.get("subject") or "").strip()
                    predicate = str(group.get("predicate") or "").strip()
                    versions: list[ClaimVersionRecord] = group.get("versions") or []
                    if not subject or not versions:
                        continue

                    key = f"claim:{normalize_key('claim', f'{subject} {predicate}')}"
                    existing = await repo.get_by_key(MemoryKind.CLAIM.value, key)
                    existing_payload = (existing.payload if existing else None) or {}
                    # A first observation is stored even when it is alone: without it a
                    # later run has nothing to supersede or contradict against, and
                    # temporal research would be impossible. The selection that keeps
                    # this from becoming a second copy of the claim table happens
                    # upstream — the caller passes a ranked, capped set of facts.
                    merged: list[dict[str, Any]] = list(
                        existing_payload.get("versions") or []
                    )
                    for version in versions:
                        merged = merge_versions(merged, version)

                    report = conflict_report(merged)
                    current = report.get("current") or (merged[0] if merged else {})
                    text = str(current.get("text") or "").strip() or (
                        f"{subject} {predicate}: "
                        f"{current.get('value') or 'value unknown'}"
                    )
                    sources = sorted(
                        {
                            str(source)
                            for version in report["versions"]
                            for source in version.get("sources", [])
                        }
                    )
                    await repo.upsert(
                        kind=MemoryKind.CLAIM.value,
                        key=key,
                        text=text,
                        payload={
                            "subject": subject,
                            "predicate": predicate,
                            "status": report["status"],
                            "versions": report["versions"],
                            "conflicts": len(report["conflicts"]),
                            "sources": sources,
                            "learned_in_session": session_id,
                        },
                        importance=max(
                            0.6,
                            importance_for(
                                MemoryKind.CLAIM.value,
                                confidence=float(current.get("confidence") or 0.6),
                                boost=0.12,
                            ),
                        ),
                        confidence=float(current.get("confidence") or 0.6),
                        source_session_id=session_id,
                    )

                    summary.updated_facts += 1
                    if existing is None:
                        summary.new_facts += 1
                    status = report["status"]
                    summary.statuses[status] = summary.statuses.get(status, 0) + 1
                    if status == STATUS_CONFLICTING:
                        summary.conflicting += 1
                    elif status == STATUS_SUPERSEDED:
                        summary.superseded += 1
                    elif status == STATUS_NEEDS_VERIFICATION:
                        summary.needs_verification += 1
                await db.commit()
        except Exception as exc:  # noqa: BLE001 — memory must never break a run
            logger.warning(
                f"Claim version memory failed ({type(exc).__name__}: {exc})."
            )
            return summary

        logger.info(
            f"Memory versions after {session_id}: {summary.updated_facts} fact(s) — "
            f"{summary.conflicting} conflicting, {summary.superseded} superseded, "
            f"{summary.needs_verification} needing verification."
        )
        return summary

    async def versioned_claims(
        self,
        statuses: list[str] | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Remembered facts that moved or conflict, newest first.

        Filtered in Python over the (capped) store rather than by JSON path: the store
        holds at most ``MEMORY_MAX_ITEMS`` rows, and this keeps the query portable
        between SQLite and PostgreSQL.
        """
        wanted = set(statuses or ())
        async with get_session_factory()() as db:
            items = await MemoryRepository(db).list_items(
                kind=MemoryKind.CLAIM.value, limit=max(1, limit)
            )

        results: list[dict[str, Any]] = []
        for item in items:
            payload = item.payload or {}
            versions = payload.get("versions") or []
            if not versions:
                continue
            status = str(payload.get("status") or "active")
            if wanted and status not in wanted:
                continue
            results.append(
                {
                    **_to_record(item).to_dict(),
                    "subject": payload.get("subject"),
                    "predicate": payload.get("predicate"),
                    "status": status,
                    "versions": versions,
                    "conflicts": int(payload.get("conflicts") or 0),
                    "sources": payload.get("sources") or [],
                    "report": conflict_report(versions),
                }
            )
        return results

    async def items_for_session(
        self, session_id: str, limit: int = 200
    ) -> list[dict[str, Any]]:
        """Everything this run learned, so a finished investigation can show it."""
        async with get_session_factory()() as db:
            items = await MemoryRepository(db).list_items(limit=max(1, limit))

        results: list[dict[str, Any]] = []
        for item in items:
            payload = item.payload or {}
            if item.source_session_id != session_id and payload.get(
                "learned_in_session"
            ) != session_id:
                continue
            results.append(
                {
                    **_to_record(item).to_dict(),
                    "provenance": {
                        "session_id": item.source_session_id,
                        "learned_in_session": payload.get("learned_in_session"),
                        "created_at": item.created_at.isoformat()
                        if item.created_at
                        else None,
                        "last_verified_at": item.updated_at.isoformat()
                        if item.updated_at
                        else None,
                        "status": payload.get("status"),
                        "sources": payload.get("sources") or [],
                    },
                }
            )
        return results

    # ─── forgetting ──────────────────────────────────────────────────────────
    async def decay_and_prune(self, now: datetime | None = None) -> dict[str, int]:
        """Forget items that have decayed, then enforce the size cap.

        Returns counts so the policy is observable rather than a silent deletion.
        """
        reference = now or datetime.now(timezone.utc)
        threshold = self.settings.MEMORY_MIN_WEIGHT
        removed_decayed = 0
        removed_overflow = 0

        async with get_session_factory()() as db:
            repo = MemoryRepository(db)
            items = await repo.list_items(limit=100_000)

            scored = [
                (
                    decay_weight(
                        _to_record(item),
                        now=reference,
                        half_life_days=self.settings.MEMORY_HALF_LIFE_DAYS,
                    ),
                    item,
                )
                for item in items
            ]

            survivors: list[tuple[float, Any]] = []
            for weight, item in scored:
                if should_forget(weight, threshold):
                    await repo.delete(item.id)
                    removed_decayed += 1
                else:
                    survivors.append((weight, item))

            # Cap enforcement evicts the lowest weight, so the store sheds its least
            # useful knowledge rather than refusing new knowledge it just learned.
            cap = self.settings.MEMORY_MAX_ITEMS
            if len(survivors) > cap:
                survivors.sort(key=lambda pair: pair[0])
                for _, item in survivors[: len(survivors) - cap]:
                    await repo.delete(item.id)
                    removed_overflow += 1

            await db.commit()

        result = {
            "removed_decayed": removed_decayed,
            "removed_overflow": removed_overflow,
        }
        if removed_decayed or removed_overflow:
            logger.info(
                f"Memory pruned: {removed_decayed} decayed, {removed_overflow} over cap."
            )
        return result

    # ─── read-only views (API) ───────────────────────────────────────────────
    async def list_items(
        self, kind: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[dict]:
        async with get_session_factory()() as db:
            repo = MemoryRepository(db)
            items = await repo.list_items(kind=kind, limit=limit, offset=offset)
            return [_to_record(item).to_dict() for item in items]

    async def stats(self, now: datetime | None = None) -> dict[str, Any]:
        reference = now or datetime.now(timezone.utc)
        async with get_session_factory()() as db:
            repo = MemoryRepository(db)
            counts = await repo.kind_counts()
            items = await repo.list_items(limit=100_000)

        weights = [
            decay_weight(
                _to_record(item),
                now=reference,
                half_life_days=self.settings.MEMORY_HALF_LIFE_DAYS,
            )
            for item in items
        ]
        embedded = sum(1 for item in items if item.embedding)
        return {
            "total": len(items),
            "kinds": counts,
            "embedded": embedded,
            "provider": self.provider.name,
            "mean_weight": round(sum(weights) / len(weights), 4) if weights else 0.0,
            "max_items": self.settings.MEMORY_MAX_ITEMS,
            "half_life_days": self.settings.MEMORY_HALF_LIFE_DAYS,
        }

    async def forget(self, item_id: str) -> bool:
        async with get_session_factory()() as db:
            repo = MemoryRepository(db)
            deleted = await repo.delete(item_id)
            await db.commit()
            return deleted


def memory_kinds() -> list[str]:
    """Every kind the store can hold, for API validation and the UI filter."""
    return [kind.value for kind in MemoryKind]
