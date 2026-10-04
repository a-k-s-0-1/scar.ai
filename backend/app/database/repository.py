"""Repository data access layer with typed queries and atomic operations."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import (
    Claim,
    ClaimSource,
    Contradiction,
    Decision,
    EdgeProvenance,
    EvaluationResult,
    EvaluationRun,
    KnowledgeEdge,
    KnowledgeNode,
    MemoryItem,
    ResearchAction,
    ResearchSession,
    ResearchTransition,
    RLPolicy,
    RLPrediction,
    SessionEvent,
    Source,
    utc_now,
)

# Events kept per session. A full deep run emits well under this, so the cap is
# only a guard against a pathological loop filling the database.
MAX_EVENTS_PER_SESSION = 2000


class SessionRepository:
    """Data access methods for ResearchSession entities."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        question: str,
        depth: str = "standard",
        domain: str | None = None,
        geographic_scope: str = "global",
        time_range: str | None = None,
        max_research_time_minutes: int = 5,
        min_sources_required: int = 10,
        output_format: str = "report",
        user_id: str | None = None,
    ) -> ResearchSession:
        session = ResearchSession(
            question=question,
            depth=depth,
            domain=domain,
            geographic_scope=geographic_scope,
            time_range=time_range,
            max_research_time_minutes=max_research_time_minutes,
            min_sources_required=min_sources_required,
            output_format=output_format,
            user_id=user_id,
            status="initializing",
            current_iteration=0,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(session)
        await self.db.flush()
        await self.db.refresh(session)
        return session

    async def get_by_id(
        self, session_id: str, load_relations: bool = False
    ) -> ResearchSession | None:
        stmt = select(ResearchSession).where(ResearchSession.id == session_id)
        if load_relations:
            stmt = stmt.options(
                selectinload(ResearchSession.sources),
                selectinload(ResearchSession.claims),
                selectinload(ResearchSession.nodes),
                selectinload(ResearchSession.edges),
                selectinload(ResearchSession.contradictions),
            )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_sessions(
        self, skip: int = 0, limit: int = 50
    ) -> list[ResearchSession]:
        stmt = (
            select(ResearchSession)
            .order_by(ResearchSession.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        session_id: str,
        status: str,
        error_message: str | None = None,
    ) -> ResearchSession | None:
        session = await self.get_by_id(session_id)
        if not session:
            return None
        session.status = status
        if error_message:
            session.error_message = error_message
        if status in ("completed", "stopped", "error"):
            session.completed_at = datetime.now(timezone.utc)
        await self.db.flush()
        return session

    async def increment_iteration(self, session_id: str) -> int:
        session = await self.get_by_id(session_id)
        if session:
            session.current_iteration += 1
            if session.status == "initializing":
                session.status = "running"
            await self.db.flush()
            return session.current_iteration
        return 0

    async def save_report(
        self,
        session_id: str,
        report_data: dict[str, Any],
        mark_completed: bool = True,
    ) -> None:
        """Store a report; ``mark_completed=False`` rewrites it in place.

        Re-synthesising a report for a finished run must not relabel a stopped
        session as completed, so callers that are replacing an existing report
        (rather than finishing a run) opt out of the status change.
        """
        session = await self.get_by_id(session_id)
        if session:
            session.report_data = report_data
            if mark_completed:
                session.status = "completed"
                session.completed_at = datetime.now(timezone.utc)
            await self.db.flush()

    async def delete(self, session_id: str) -> bool:
        session = await self.get_by_id(session_id)
        if not session:
            return False
        await self.db.delete(session)
        await self.db.flush()
        return True


class SessionEventRepository:
    """Append-only access to a session's durable progress events."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def append(self, session_id: str, payload: dict[str, Any]) -> int:
        """Append one event and return its per-session sequence number."""
        current_max = await self.db.execute(
            select(func.coalesce(func.max(SessionEvent.seq), 0)).where(
                SessionEvent.session_id == session_id
            )
        )
        next_seq = int(current_max.scalar_one()) + 1

        raw_iteration = payload.get("iteration")
        event = SessionEvent(
            session_id=session_id,
            seq=next_seq,
            event_type=str(payload.get("type", "unknown")),
            iteration=raw_iteration if isinstance(raw_iteration, int) else None,
            payload=payload,
        )
        self.db.add(event)

        # Trim from the front once the cap is exceeded; the oldest events are the
        # least useful for replay.
        if next_seq > MAX_EVENTS_PER_SESSION:
            cutoff = next_seq - MAX_EVENTS_PER_SESSION
            await self.db.execute(
                delete(SessionEvent).where(
                    SessionEvent.session_id == session_id, SessionEvent.seq <= cutoff
                )
            )

        await self.db.flush()
        return next_seq

    async def list_events(
        self, session_id: str, after_seq: int = 0, limit: int = 500
    ) -> list[SessionEvent]:
        """Return events in order, resuming after the client's last seen seq."""
        stmt = (
            select(SessionEvent)
            .where(
                SessionEvent.session_id == session_id,
                SessionEvent.seq > after_seq,
            )
            .order_by(SessionEvent.seq.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count(self, session_id: str) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(SessionEvent)
            .where(SessionEvent.session_id == session_id)
        )
        return int(result.scalar_one())


class MemoryRepository:
    """Data access methods for long-term memory items."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_key(self, kind: str, key: str) -> MemoryItem | None:
        stmt = select(MemoryItem).where(MemoryItem.kind == kind, MemoryItem.key == key)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        kind: str,
        key: str,
        text: str,
        payload: dict[str, Any] | None = None,
        importance: float = 0.5,
        confidence: float = 0.6,
        embedding: list[float] | None = None,
        embedding_model: str | None = None,
        source_session_id: str | None = None,
    ) -> MemoryItem:
        """Insert an item, or refresh the one already stored under this key.

        Re-learning must not create duplicates, and it must not weaken what is known:
        importance only ever rises, and an existing embedding is kept unless a new one
        was actually produced (a provider outage returns no vector, which is not a
        reason to discard the vector we already have).
        """
        existing = await self.get_by_key(kind, key)
        if existing is not None:
            existing.text = text
            if payload is not None:
                existing.payload = payload
            existing.importance = max(existing.importance, importance)
            existing.confidence = max(existing.confidence, confidence)
            if embedding:
                existing.embedding = embedding
                existing.embedding_model = embedding_model
            existing.updated_at = utc_now()
            await self.db.flush()
            return existing

        item = MemoryItem(
            kind=kind,
            key=key,
            text=text,
            payload=payload,
            importance=importance,
            confidence=confidence,
            embedding=embedding,
            embedding_model=embedding_model,
            source_session_id=source_session_id,
        )
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def list_items(
        self, kind: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[MemoryItem]:
        stmt = select(MemoryItem)
        if kind:
            stmt = stmt.where(MemoryItem.kind == kind)
        stmt = (
            stmt.order_by(MemoryItem.updated_at.desc())
            .offset(max(0, offset))
            .limit(max(1, limit))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def candidates(
        self, kinds: list[str] | None = None, limit: int = 400
    ) -> list[MemoryItem]:
        """Recent items to score against a query.

        Ranking happens in Python, so the candidate set is capped per query: without a
        cap, recall cost grows with total memory size and a long-lived project gets
        slower every run.
        """
        stmt = select(MemoryItem)
        if kinds:
            stmt = stmt.where(MemoryItem.kind.in_(kinds))
        stmt = stmt.order_by(MemoryItem.updated_at.desc()).limit(max(1, limit))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def touch(self, item_ids: list[str]) -> int:
        """Record that items were recalled; reuse is what keeps knowledge alive."""
        if not item_ids:
            return 0
        stmt = select(MemoryItem).where(MemoryItem.id.in_(item_ids))
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        now = utc_now()
        for item in items:
            item.hits += 1
            item.last_used_at = now
        await self.db.flush()
        return len(items)

    async def delete(self, item_id: str) -> bool:
        item = await self.db.get(MemoryItem, item_id)
        if item is None:
            return False
        await self.db.delete(item)
        await self.db.flush()
        return True

    async def count(self, kind: str | None = None) -> int:
        stmt = select(func.count()).select_from(MemoryItem)
        if kind:
            stmt = stmt.where(MemoryItem.kind == kind)
        result = await self.db.execute(stmt)
        return int(result.scalar() or 0)

    async def kind_counts(self) -> dict[str, int]:
        stmt = select(MemoryItem.kind, func.count()).group_by(MemoryItem.kind)
        result = await self.db.execute(stmt)
        return {str(kind): int(total) for kind, total in result.all()}


class SourceRepository:
    """Data access methods for Source entities."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        session_id: str,
        url: str,
        title: str | None,
        content: str | None,
        source_type: str = "article",
        credibility_score: float = 0.5,
        published_at: datetime | None = None,
        content_hash: str | None = None,
    ) -> Source:
        source = Source(
            session_id=session_id,
            url=url,
            title=title,
            content=content,
            source_type=source_type,
            credibility_score=credibility_score,
            published_at=published_at,
            content_hash=content_hash,
        )
        self.db.add(source)
        await self.db.flush()
        await self.db.refresh(source)
        return source

    async def get_by_session(self, session_id: str) -> list[Source]:
        stmt = (
            select(Source)
            .where(Source.session_id == session_id)
            .order_by(Source.created_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_existing_urls(self, session_id: str) -> set[str]:
        stmt = select(Source.url).where(Source.session_id == session_id)
        result = await self.db.execute(stmt)
        return set(result.scalars().all())


class ClaimRepository:
    """Data access methods for Claims and ClaimSources."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        session_id: str,
        claim_text: str,
        subject: str | None = None,
        predicate: str | None = None,
        obj: str | None = None,
        confidence: str = "medium",
    ) -> Claim:
        claim = Claim(
            session_id=session_id,
            claim=claim_text,
            subject=subject,
            predicate=predicate,
            object=obj,
            confidence=confidence,
            status="active",
        )
        self.db.add(claim)
        await self.db.flush()
        await self.db.refresh(claim)
        return claim

    async def link_source(
        self,
        claim_id: str,
        source_id: str,
        support_type: str = "supports",
        confidence: float = 0.8,
    ) -> ClaimSource:
        link = ClaimSource(
            claim_id=claim_id,
            source_id=source_id,
            support_type=support_type,
            confidence=confidence,
        )
        self.db.add(link)
        await self.db.flush()
        return link

    async def get_by_session(self, session_id: str) -> list[Claim]:
        stmt = (
            select(Claim)
            .where(Claim.session_id == session_id)
            .options(selectinload(Claim.source_links).selectinload(ClaimSource.source))
            .order_by(Claim.created_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_links_for_claims(
        self, claim_ids: list[str]
    ) -> dict[str, list[ClaimSource]]:
        """Source links per claim id, loaded on demand.

        The research loop holds claim objects created inside a session that has since
        closed, so their relationships cannot be lazy-loaded; anything that needs a
        claim's sources after that point has to ask for them explicitly.
        """
        if not claim_ids:
            return {}
        stmt = (
            select(ClaimSource)
            .where(ClaimSource.claim_id.in_(claim_ids))
            .options(selectinload(ClaimSource.source))
        )
        result = await self.db.execute(stmt)
        grouped: dict[str, list[ClaimSource]] = {}
        for link in result.scalars().all():
            grouped.setdefault(link.claim_id, []).append(link)
        return grouped


class KnowledgeRepository:
    """Data access methods for Knowledge graph nodes and edges."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_create_node(
        self,
        session_id: str,
        entity: str,
        entity_type: str = "concept",
        description: str | None = None,
    ) -> KnowledgeNode:
        cleaned_entity = entity.strip()
        stmt = select(KnowledgeNode).where(
            KnowledgeNode.session_id == session_id,
            func.lower(KnowledgeNode.entity) == cleaned_entity.lower(),
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        node = KnowledgeNode(
            session_id=session_id,
            entity=cleaned_entity,
            entity_type=entity_type,
            description=description,
        )
        self.db.add(node)
        await self.db.flush()
        await self.db.refresh(node)
        return node

    async def add_edge(
        self,
        session_id: str,
        source_node_id: str,
        target_node_id: str,
        relationship_type: str,
        strength: float = 0.7,
    ) -> KnowledgeEdge:
        # Check if edge already exists between these nodes
        stmt = select(KnowledgeEdge).where(
            KnowledgeEdge.session_id == session_id,
            KnowledgeEdge.source_node_id == source_node_id,
            KnowledgeEdge.target_node_id == target_node_id,
            KnowledgeEdge.relationship_type == relationship_type,
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        edge = KnowledgeEdge(
            session_id=session_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relationship_type=relationship_type,
            strength=strength,
        )
        self.db.add(edge)
        await self.db.flush()
        await self.db.refresh(edge)
        return edge

    async def upsert_edge_provenance(
        self, session_id: str, edge_id: str, payload: dict[str, Any]
    ) -> EdgeProvenance:
        """Store or widen the provenance of one edge.

        The same relationship is asserted by many claims across iterations, so the
        incoming payload is *merged* into whatever is already stored instead of
        replacing it; otherwise the last claim to arrive would erase the evidence of
        every earlier one.
        """
        # Imported here, not at module scope: ``app.services.ikf`` imports this
        # module, so a top-level import would close a cycle through the package
        # __init__ and fail on the second import of a cold process.
        from app.services.ikf.provenance import merge_provenance

        stmt = select(EdgeProvenance).where(
            EdgeProvenance.session_id == session_id,
            EdgeProvenance.edge_id == edge_id,
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            existing.payload = merge_provenance(existing.payload, payload)
            await self.db.flush()
            return existing

        record = EdgeProvenance(
            session_id=session_id, edge_id=edge_id, payload=merge_provenance(None, payload)
        )
        self.db.add(record)
        await self.db.flush()
        await self.db.refresh(record)
        return record

    async def get_edge_provenance(self, session_id: str) -> dict[str, dict[str, Any]]:
        """Provenance payloads for a session, keyed by edge id."""
        stmt = select(EdgeProvenance).where(EdgeProvenance.session_id == session_id)
        result = await self.db.execute(stmt)
        return {record.edge_id: record.payload for record in result.scalars().all()}

    async def get_graph(
        self, session_id: str
    ) -> tuple[list[KnowledgeNode], list[KnowledgeEdge]]:
        nodes_stmt = select(KnowledgeNode).where(KnowledgeNode.session_id == session_id)
        edges_stmt = select(KnowledgeEdge).where(KnowledgeEdge.session_id == session_id)
        nodes_res = await self.db.execute(nodes_stmt)
        edges_res = await self.db.execute(edges_stmt)
        return list(nodes_res.scalars().all()), list(edges_res.scalars().all())


class ContradictionRepository:
    """Data access methods for Contradictions."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        session_id: str,
        claim_1_id: str,
        claim_2_id: str,
        severity: str = "medium",
        resolution_note: str | None = None,
    ) -> Contradiction:
        # Check for existing duplicate contradiction
        stmt = select(Contradiction).where(
            Contradiction.session_id == session_id,
            (
                (Contradiction.claim_1_id == claim_1_id)
                & (Contradiction.claim_2_id == claim_2_id)
            )
            | (
                (Contradiction.claim_1_id == claim_2_id)
                & (Contradiction.claim_2_id == claim_1_id)
            ),
        )
        res = await self.db.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            return existing

        contra = Contradiction(
            session_id=session_id,
            claim_1_id=claim_1_id,
            claim_2_id=claim_2_id,
            severity=severity,
            resolved=False,
            resolution_note=resolution_note,
        )
        self.db.add(contra)
        await self.db.flush()
        await self.db.refresh(contra)
        return contra

    async def get_by_session(self, session_id: str) -> list[Contradiction]:
        stmt = (
            select(Contradiction)
            .where(Contradiction.session_id == session_id)
            .options(
                selectinload(Contradiction.claim_1),
                selectinload(Contradiction.claim_2),
            )
            .order_by(Contradiction.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


class DecisionRepository:
    """Data access methods for Decisions and ResearchActions."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log_decision(
        self,
        session_id: str,
        iteration_number: int,
        knowledge_state_snapshot: dict[str, Any],
        available_actions: list[str],
        selected_action: str,
        action_reasoning: str,
        reward_signal: float | None = None,
    ) -> Decision:
        decision = Decision(
            session_id=session_id,
            iteration_number=iteration_number,
            knowledge_state_snapshot=knowledge_state_snapshot,
            available_actions=available_actions,
            selected_action=selected_action,
            action_reasoning=action_reasoning,
            reward_signal=reward_signal,
        )
        self.db.add(decision)
        await self.db.flush()
        return decision

    async def get_by_session(self, session_id: str) -> list[Decision]:
        """Every decision for a session, oldest first (replay order)."""
        stmt = (
            select(Decision)
            .where(Decision.session_id == session_id)
            .order_by(Decision.iteration_number.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def log_action(
        self,
        session_id: str,
        iteration_number: int,
        action_type: str,
        query: str | None = None,
        result_summary: str | None = None,
        sources_found: int = 0,
        new_claims_extracted: int = 0,
        information_gain: float | None = None,
        duration_seconds: int | None = None,
    ) -> ResearchAction:
        action = ResearchAction(
            session_id=session_id,
            iteration_number=iteration_number,
            action_type=action_type,
            query=query,
            result_summary=result_summary,
            sources_found=sources_found,
            new_claims_extracted=new_claims_extracted,
            information_gain=information_gain,
            duration_seconds=duration_seconds,
        )
        self.db.add(action)
        await self.db.flush()
        return action


class TransitionRepository:
    """Data access for the learnable ``state -> action -> reward -> next_state`` rows."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def upsert(
        self,
        *,
        session_id: str,
        iteration: int,
        state_before: dict[str, Any],
        state_after: dict[str, Any] | None,
        action_type: str,
        action_parameters: dict[str, Any] | None = None,
        observation: dict[str, Any] | None = None,
        reward: float = 0.0,
        reward_components: dict[str, Any] | None = None,
        information_gain: float = 0.0,
        coverage_before: float = 0.0,
        coverage_after: float = 0.0,
        contradictions_before: int = 0,
        contradictions_after: int = 0,
        sources_added: int = 0,
        claims_added: int = 0,
        execution_time: float = 0.0,
        policy_source: str = "JEV",
        done: bool = False,
        state_hash: str | None = None,
        state_bytes: int = 0,
    ) -> ResearchTransition:
        """Insert this iteration's transition, replacing one already stored for it.

        A run that is somehow replayed must not leave two contradictory transitions
        for the same iteration, which would double-count that step in every dataset.
        """
        existing = await self.get_transition(session_id, iteration)
        if existing is not None:
            existing.state_before = state_before
            existing.state_after = state_after
            existing.state_hash = state_hash
            existing.state_bytes = state_bytes
            existing.action_type = action_type
            existing.action_parameters = action_parameters
            existing.observation = observation
            existing.reward = reward
            existing.reward_components = reward_components
            existing.information_gain = information_gain
            existing.coverage_before = coverage_before
            existing.coverage_after = coverage_after
            existing.contradictions_before = contradictions_before
            existing.contradictions_after = contradictions_after
            existing.sources_added = sources_added
            existing.claims_added = claims_added
            existing.execution_time = execution_time
            existing.policy_source = policy_source
            existing.done = done
            await self.db.flush()
            return existing

        transition = ResearchTransition(
            session_id=session_id,
            iteration=iteration,
            state_before=state_before,
            state_after=state_after,
            state_hash=state_hash,
            state_bytes=state_bytes,
            action_type=action_type,
            action_parameters=action_parameters,
            observation=observation,
            reward=reward,
            reward_components=reward_components,
            information_gain=information_gain,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            contradictions_before=contradictions_before,
            contradictions_after=contradictions_after,
            sources_added=sources_added,
            claims_added=claims_added,
            execution_time=execution_time,
            policy_source=policy_source,
            done=done,
        )
        self.db.add(transition)
        await self.db.flush()
        await self.db.refresh(transition)
        return transition

    async def get_transition(
        self, session_id: str, iteration: int
    ) -> ResearchTransition | None:
        stmt = select(ResearchTransition).where(
            ResearchTransition.session_id == session_id,
            ResearchTransition.iteration == iteration,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_session(
        self, session_id: str, limit: int | None = None
    ) -> list[ResearchTransition]:
        stmt = (
            select(ResearchTransition)
            .where(ResearchTransition.session_id == session_id)
            .order_by(ResearchTransition.iteration.asc())
        )
        if limit is not None:
            stmt = stmt.limit(max(1, limit))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_transitions(
        self, session_ids: list[str] | None = None, limit: int = 5000
    ) -> list[ResearchTransition]:
        """Transitions ordered for dataset construction (session, then iteration)."""
        stmt = select(ResearchTransition)
        if session_ids:
            stmt = stmt.where(ResearchTransition.session_id.in_(session_ids))
        stmt = (
            stmt.order_by(
                ResearchTransition.session_id.asc(),
                ResearchTransition.iteration.asc(),
            ).limit(max(1, limit))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def session_ids_with_transitions(self) -> list[str]:
        stmt = select(ResearchTransition.session_id).distinct()
        result = await self.db.execute(stmt)
        return sorted(str(value) for value in result.scalars().all())

    async def count(self, session_id: str | None = None) -> int:
        stmt = select(func.count()).select_from(ResearchTransition)
        if session_id:
            stmt = stmt.where(ResearchTransition.session_id == session_id)
        result = await self.db.execute(stmt)
        return int(result.scalar() or 0)

    async def completed_session_ids(self) -> list[str]:
        """Sessions owning at least one terminal transition — dataset-ready runs."""
        stmt = (
            select(ResearchTransition.session_id)
            .where(ResearchTransition.done.is_(True))
            .distinct()
        )
        result = await self.db.execute(stmt)
        return sorted(str(value) for value in result.scalars().all())

    async def finished_session_ids(self) -> list[str]:
        """Sessions whose run actually finished (status-based, no transitions needed).

        This is the backfill's candidate list: historical runs predate transitions
        entirely, so "has a done transition" can never describe them.
        """
        from app.database.models import ResearchSession

        stmt = select(ResearchSession.id).where(
            ResearchSession.status == "completed"
        )
        result = await self.db.execute(stmt)
        return sorted(str(value) for value in result.scalars().all())


class PolicyRepository:
    """Data access for stored offline policies."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        name: str,
        algorithm: str,
        payload: dict[str, Any],
        version: str = "1.0",
        dataset_version: str | None = None,
        dataset_hash: str | None = None,
        baseline: str = "JEV",
        samples: int = 0,
        sessions: int = 0,
        metrics: dict[str, Any] | None = None,
        notes: str | None = None,
        active: bool = False,
    ) -> RLPolicy:
        policy = RLPolicy(
            name=name,
            version=version,
            algorithm=algorithm,
            dataset_version=dataset_version,
            dataset_hash=dataset_hash,
            baseline=baseline,
            samples=samples,
            sessions=sessions,
            payload=payload,
            metrics=metrics,
            notes=notes,
            active=active,
        )
        self.db.add(policy)
        await self.db.flush()
        await self.db.refresh(policy)
        return policy

    async def get_by_id(self, policy_id: str) -> RLPolicy | None:
        return await self.db.get(RLPolicy, policy_id)

    async def get_active(self) -> RLPolicy | None:
        stmt = (
            select(RLPolicy)
            .where(RLPolicy.active.is_(True))
            .order_by(RLPolicy.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_policies(self, limit: int = 50) -> list[RLPolicy]:
        stmt = select(RLPolicy).order_by(RLPolicy.created_at.desc()).limit(max(1, limit))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def set_active(self, policy_id: str) -> RLPolicy | None:
        """Promote one policy, demoting every other in the same transaction."""
        stmt = select(RLPolicy).where(RLPolicy.active.is_(True))
        result = await self.db.execute(stmt)
        for existing in result.scalars().all():
            existing.active = False
        policy = await self.get_by_id(policy_id)
        if policy is None:
            return None
        policy.active = True
        await self.db.flush()
        return policy

    async def count(self) -> int:
        result = await self.db.execute(select(func.count()).select_from(RLPolicy))
        return int(result.scalar() or 0)


class PredictionRepository:
    """Data access for shadow-mode RL predictions."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        session_id: str,
        iteration: int,
        state_key: str,
        jev_action: str,
        rl_action: str,
        state: dict[str, Any] | None = None,
        policy_id: str | None = None,
        jev_reasoning: str | None = None,
        jev_expected_value: float | None = None,
        rl_expected_value: float | None = None,
        rl_scores: dict[str, Any] | None = None,
        rl_support: int = 0,
        fallback: bool = False,
        estimated_rl_reward: float | None = None,
        disagreement: bool = False,
    ) -> RLPrediction:
        prediction = RLPrediction(
            session_id=session_id,
            iteration=iteration,
            policy_id=policy_id,
            state_key=state_key,
            state=state,
            jev_action=jev_action,
            jev_reasoning=jev_reasoning,
            jev_expected_value=jev_expected_value,
            rl_action=rl_action,
            rl_expected_value=rl_expected_value,
            rl_scores=rl_scores,
            rl_support=rl_support,
            fallback=fallback,
            estimated_rl_reward=estimated_rl_reward,
            disagreement=disagreement,
        )
        self.db.add(prediction)
        await self.db.flush()
        await self.db.refresh(prediction)
        return prediction

    async def update_reward(self, prediction_id: str, actual_reward: float) -> None:
        """Fill in what the JEV action actually earned, once the next step knows."""
        prediction = await self.db.get(RLPrediction, prediction_id)
        if prediction is not None:
            prediction.actual_reward = actual_reward
            await self.db.flush()

    async def get_by_session(
        self, session_id: str, limit: int = 500
    ) -> list[RLPrediction]:
        stmt = (
            select(RLPrediction)
            .where(RLPrediction.session_id == session_id)
            .order_by(RLPrediction.iteration.asc())
            .limit(max(1, limit))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def latest_for_session(self, session_id: str) -> RLPrediction | None:
        stmt = (
            select(RLPrediction)
            .where(RLPrediction.session_id == session_id)
            .order_by(RLPrediction.iteration.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def agreement_stats(self) -> dict[str, int]:
        """Agreement/disagreement counts across every recorded shadow prediction."""
        total_stmt = select(func.count()).select_from(RLPrediction)
        disagreement_stmt = (
            select(func.count())
            .select_from(RLPrediction)
            .where(RLPrediction.disagreement.is_(True))
        )
        total = int((await self.db.execute(total_stmt)).scalar() or 0)
        disagreements = int((await self.db.execute(disagreement_stmt)).scalar() or 0)
        return {
            "total": total,
            "disagreements": disagreements,
            "agreements": max(0, total - disagreements),
        }


class EvaluationRepository:
    """Data access for evaluation runs and their per-scope results."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_run(
        self,
        *,
        policy: str,
        baseline: str | None,
        dataset_version: str,
        dataset_hash: str | None,
        dataset_size: int,
        sessions: int,
        max_steps: int | None,
        status: str = "completed",
        config: dict[str, Any] | None = None,
        aggregate: dict[str, Any] | None = None,
        comparison: dict[str, Any] | None = None,
        notes: list[str] | None = None,
    ) -> EvaluationRun:
        run = EvaluationRun(
            policy=policy,
            baseline=baseline,
            dataset_version=dataset_version,
            dataset_hash=dataset_hash,
            dataset_size=dataset_size,
            sessions=sessions,
            max_steps=max_steps,
            status=status,
            config=config,
            aggregate=aggregate,
            comparison=comparison,
            notes=notes,
            completed_at=utc_now() if status == "completed" else None,
        )
        self.db.add(run)
        await self.db.flush()
        await self.db.refresh(run)
        return run

    async def add_result(
        self,
        run_id: str,
        *,
        scope: str,
        key: str,
        sample_size: int,
        metrics: dict[str, Any],
    ) -> EvaluationResult:
        result = EvaluationResult(
            run_id=run_id,
            scope=scope,
            key=key,
            sample_size=sample_size,
            metrics=metrics,
        )
        self.db.add(result)
        await self.db.flush()
        return result

    async def list_runs(self, limit: int = 20) -> list[EvaluationRun]:
        stmt = (
            select(EvaluationRun)
            .order_by(EvaluationRun.created_at.desc())
            .limit(max(1, limit))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_run(self, run_id: str) -> EvaluationRun | None:
        return await self.db.get(EvaluationRun, run_id)

    async def list_results(self, run_id: str) -> list[EvaluationResult]:
        stmt = (
            select(EvaluationResult)
            .where(EvaluationResult.run_id == run_id)
            .order_by(EvaluationResult.created_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_runs(self) -> int:
        result = await self.db.execute(select(func.count()).select_from(EvaluationRun))
        return int(result.scalar() or 0)
