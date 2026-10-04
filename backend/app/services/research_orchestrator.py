"""Core Research Loop Orchestrator coordinating SearchAgent, ClaimExtractor, IKF, JEV and ReportGenerator."""

import asyncio
import time
from dataclasses import asdict
from typing import Any

from app.api.errors import SessionBudgetExceededError
from app.config import get_settings
from app.database.models import Contradiction
from app.database.repository import (
    ClaimRepository,
    ContradictionRepository,
    KnowledgeRepository,
    SessionRepository,
    SourceRepository,
)
from app.database.session import async_session_maker
from app.integrations.llm_router import llm_router
from app.services.claim_extractor import ClaimExtractor
from app.services.contradiction_detector import ContradictionDetector
from app.services.decision_engine import (
    NOVELTY_PLATEAU_GAIN,
    ActionType,
    DecisionEngine,
    KnowledgeState,
)
from app.services.depth_config import get_depth_profile
from app.services.facet_planner import FacetPlanner, classify_facet_text
from app.services.ikf import (
    EntityResolver,
    KnowledgeIndex,
    build_knowledge_index,
    extraction_confidence,
)
from app.services.knowledge_fusion import KnowledgeFusion
from app.services.memory import LongTermMemory, claim_version_from_ikf
from app.services.metrics import compute_coverage_estimate, compute_information_gain
from app.services.report_generator import ReportGenerator
from app.services.rl import TrajectoryRecorder, count_duplicate_claims
from app.services.search_agent import SearchAgent
from app.services.search_memory import SearchMemory
from app.utils.logger import logger
from app.ws.managers import ws_manager

settings = get_settings()


class ResearchOrchestrator:
    """Coordinates the autonomous research loop, driving iterative discovery and self-correction."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

    async def run(self) -> None:
        """Run the session and always release its LLM budget afterwards.

        Per-session budgets are keyed by session id, so without this the router's
        registry would keep an entry for every investigation ever run.
        """
        try:
            await self._run()
        finally:
            llm_router.release_session(self.session_id)

    async def _run(self) -> None:
        """Main asynchronous entrypoint driving the multi-iteration research session."""
        start_time = time.time()
        logger.info(f"Starting research orchestrator for session: {self.session_id}")

        async with async_session_maker() as db:
            session_repo = SessionRepository(db)
            session = await session_repo.get_by_id(self.session_id)
            if not session:
                logger.error(
                    f"Cannot run research: Session {self.session_id} not found."
                )
                return

            await session_repo.update_status(self.session_id, status="running")
            await db.commit()

        # Broadcast initialization
        await ws_manager.broadcast(
            self.session_id,
            {
                "type": "initialized",
                "session_id": self.session_id,
                "status": "running",
                "question": session.question,
            },
        )

        profile = get_depth_profile(session.depth)
        max_iterations = profile.max_iterations
        current_query = session.question
        # Which dimension of the question the current query is meant to fill, so
        # the search outcome can be attributed back to that facet.
        current_facet: str | None = None
        previous_claims_count = 0
        info_gain = 1.0
        stop_reason: str | None = None
        # Signals the stopping policy needs beyond a single iteration's numbers.
        previous_coverage = 0.0
        plateau_iterations = 0
        last_verified_signature: frozenset[tuple[str, str]] | None = None

        search_agent = SearchAgent(
            self.session_id, max_queries=session.min_sources_required * 3
        )
        # ─── V2 2.3 / 2.7 — offline learning hooks ────────────────────────────
        # The recorder writes one state/action/reward/next-state transition per
        # iteration and asks the offline policy what it would have done, without
        # ever acting on the answer. It is wrapped so telemetry can never cost a
        # session, and ``executed_action`` tracks what this iteration actually ran
        # (JEV's choice one step earlier) so the reward lands on the right action.
        trajectory_recorder = TrajectoryRecorder(
            self.session_id,
            question=session.question,
            depth=session.depth,
            max_iterations=max_iterations,
            min_sources_required=session.min_sources_required,
            max_research_time_minutes=session.max_research_time_minutes,
            enabled=settings.RL_TRAJECTORY_ENABLED,
            shadow_enabled=settings.RL_SHADOW_ENABLED,
        )
        executed_action = ActionType.SEARCH.value
        executed_action_parameters: dict[str, Any] = {
            "query": session.question,
            "facet": None,
        }
        claim_extractor = ClaimExtractor(self.session_id)
        knowledge_fusion = KnowledgeFusion(self.session_id)
        contradiction_detector = ContradictionDetector(self.session_id)
        decision_engine = DecisionEngine(self.session_id)
        report_generator = ReportGenerator(self.session_id)
        facet_planner = FacetPlanner(session.question, session.depth)
        search_memory = SearchMemory()
        # IKF 2.0: one entity resolver for the whole run, so an alias learned in
        # iteration 2 still resolves in iteration 7, plus the evidence/versioning index
        # rebuilt each iteration (strength moves as corroboration arrives).
        entity_resolver = EntityResolver()
        knowledge_index: KnowledgeIndex | None = None
        temporal_versions_suppressed = 0

        # ─── V2 2.1 — recall before the first search ─────────────────────────
        # Everything in V1 started each session from nothing, so a dead end cost one
        # search per run and a learned alias ("IBM" = "International Business
        # Machines") was relearned every time. Recalling here is what makes iteration
        # 1 of this run benefit from iteration 7 of an earlier one.
        long_term_memory = LongTermMemory()
        memory_recall: list[dict[str, Any]] = []
        dead_ends_seeded = 0
        entity_alias_sets = 0
        if long_term_memory.enabled:
            try:
                recalled = await long_term_memory.recall(session.question)
                memory_recall = [item.to_dict() for item in recalled]
                aliases = await long_term_memory.aliases()
                if aliases:
                    entity_resolver.seed(aliases)
                entity_alias_sets = len(aliases)
                dead_ends_seeded = search_memory.prime_dead_ends(
                    await long_term_memory.avoided_queries()
                )
                logger.info(
                    f"Session {self.session_id} recalled {len(memory_recall)} memory "
                    f"item(s), seeded {dead_ends_seeded} known dead end(s) and "
                    f"{len(aliases)} entity alias set(s)."
                )
            except Exception as exc:  # noqa: BLE001 — memory must never block research
                logger.warning(
                    f"Memory recall failed ({type(exc).__name__}: {exc}); "
                    f"continuing without cross-session knowledge."
                )
            await ws_manager.broadcast(
                self.session_id,
                {
                    "type": "memory_recalled",
                    "items": memory_recall,
                    "dead_ends_seeded": dead_ends_seeded,
                    "entities_seeded": entity_alias_sets,
                },
            )

        try:
            for iteration in range(1, max_iterations + 1):
                # Check cancellation or timeout
                async with async_session_maker() as db:
                    s_repo = SessionRepository(db)
                    current_s = await s_repo.get_by_id(self.session_id)
                    if not current_s or current_s.status in ("stopped", "error"):
                        logger.info(
                            f"Session {self.session_id} aborted (status: {current_s.status if current_s else 'deleted'})"
                        )
                        await ws_manager.broadcast(
                            self.session_id, {"type": "stopped", "by": "user"}
                        )
                        return
                    await s_repo.increment_iteration(self.session_id)
                    await db.commit()

                elapsed_minutes = (time.time() - start_time) / 60.0
                if elapsed_minutes >= session.max_research_time_minutes:
                    stop_reason = (
                        f"Reached maximum allowed research time "
                        f"({session.max_research_time_minutes} min)."
                    )
                    logger.info(
                        f"Session {self.session_id} hit timeout limit of {session.max_research_time_minutes}m"
                    )
                    break

                logger.info(
                    f"--- Session {self.session_id} Iteration {iteration}/{max_iterations} ---"
                )
                iteration_started = time.time()

                # 1. Search Step
                search_payload: dict[str, Any] = {
                    "type": "search_started",
                    "iteration": iteration,
                    "query": current_query,
                }
                if current_facet:
                    search_payload["facet"] = current_facet
                await ws_manager.broadcast(self.session_id, search_payload)

                async with async_session_maker() as db:
                    new_sources = await search_agent.search(
                        query=current_query, db=db, max_results=8
                    )
                    await db.commit()

                async with async_session_maker() as db:
                    source_repo = SourceRepository(db)
                    all_sources = await source_repo.get_by_session(self.session_id)
                    total_sources_count = len(all_sources)

                await ws_manager.broadcast(
                    self.session_id,
                    {
                        "type": "sources_found",
                        "iteration": iteration,
                        "count": len(new_sources),
                        "total_sources": total_sources_count,
                    },
                )

                # 2. Claim Extraction Step
                new_claims = []
                if new_sources:
                    await ws_manager.broadcast(
                        self.session_id,
                        {
                            "type": "extraction_started",
                            "iteration": iteration,
                            "sources_count": len(new_sources),
                        },
                    )

                    async with async_session_maker() as db:
                        new_claims = await claim_extractor.extract_from_sources(
                            sources=new_sources,
                            question=session.question,
                            db=db,
                        )
                        await db.commit()

                async with async_session_maker() as db:
                    claim_repo = ClaimRepository(db)
                    all_claims = await claim_repo.get_by_session(self.session_id)
                    total_claims_count = len(all_claims)

                await ws_manager.broadcast(
                    self.session_id,
                    {
                        "type": "claims_extracted",
                        "iteration": iteration,
                        "count": len(new_claims),
                        "total_claims": total_claims_count,
                    },
                )

                # Remember what this query bought, so the planner never pays for
                # the same (or an already empty) query twice.
                search_memory.record(
                    current_query,
                    new_sources=len(new_sources),
                    new_claims=len(new_claims),
                    iteration=iteration,
                    facet=current_facet or "",
                )

                # 3. Knowledge Fusion Step (IKF)
                new_nodes = 0
                new_edges = 0
                if new_claims:
                    async with async_session_maker() as db:
                        new_nodes, new_edges = await knowledge_fusion.fuse_claims(
                            new_claims,
                            db=db,
                            resolver=entity_resolver,
                            # Yesterday's index still describes the best evidence
                            # available for these claims; the new index below replaces
                            # it for the next iteration.
                            evidence=(
                                knowledge_index.evidence if knowledge_index else None
                            ),
                        )
                        await db.commit()

                async with async_session_maker() as db:
                    know_repo = KnowledgeRepository(db)
                    nodes, edges = await know_repo.get_graph(self.session_id)

                await ws_manager.broadcast(
                    self.session_id,
                    {
                        "type": "knowledge_updated",
                        "nodes": len(nodes),
                        "edges": len(edges),
                    },
                )

                # 3b. Facet coverage: which dimensions of the question the claims
                # actually answer, and which still have no evidence at all.
                facet_snapshot = facet_planner.observe(all_claims, iteration=iteration)
                await ws_manager.broadcast(
                    self.session_id,
                    {
                        "type": "facet_updated",
                        "iteration": iteration,
                        "facet_coverage": facet_snapshot.coverage,
                        "facets": [
                            asdict(entry) for entry in facet_snapshot.facets
                        ],
                        "facet_gaps": list(facet_snapshot.gaps),
                    },
                )

                # 3c. IKF 2.0 index over everything gathered so far: canonical
                # entities, evidence strength per claim, and claim versioning. This is
                # what lets the loop tell a moving fact from a real disagreement.
                async with async_session_maker() as db:
                    knowledge_index = await build_knowledge_index(
                        self.session_id, db, resolver=entity_resolver
                    )
                await ws_manager.broadcast(
                    self.session_id,
                    {
                        "type": "ikf_updated",
                        "iteration": iteration,
                        "evidence": knowledge_index.evidence_stats,
                        "versions": knowledge_index.version_stats,
                        "entities": knowledge_index.resolver.stats(),
                    },
                )

                # 4. Contradiction & Gap Detection
                # This stage issues up to 15 LLM calls, so a spent time budget must
                # short-circuit it: the loop's own time check only runs between
                # iterations, which let slow (rate-limited) sessions overrun.
                async with async_session_maker() as db:
                    elapsed_minutes = (time.time() - start_time) / 60.0
                    if elapsed_minutes >= session.max_research_time_minutes:
                        contradictions, gaps = [], []
                        logger.warning(
                            f"Session {self.session_id} skipped contradiction detection: "
                            f"time budget spent ({elapsed_minutes:.1f}m of {session.max_research_time_minutes}m)."
                        )
                    else:
                        contradictions = (
                            await contradiction_detector.detect_contradictions(db=db)
                        )
                        # A pair that the versioning layer recognises as one fact
                        # observed twice is not a disagreement to verify.
                        contradictions, suppressed = self._drop_temporal_versions(
                            contradictions, knowledge_index
                        )
                        if suppressed:
                            temporal_versions_suppressed += suppressed
                            logger.info(
                                f"Session {self.session_id}: suppressed {suppressed} "
                                f"temporal version pair(s) that V1 would have treated "
                                f"as contradictions."
                            )
                        gaps = await contradiction_detector.identify_knowledge_gaps(
                            db=db, question=session.question
                        )
                    await db.commit()

                if contradictions:
                    await ws_manager.broadcast(
                        self.session_id,
                        {
                            "type": "contradiction_detected",
                            "count": len(contradictions),
                            "severity": (
                                contradictions[0].severity
                                if contradictions
                                else "medium"
                            ),
                        },
                    )

                # 5. Metrics & JEV Decision Engine
                previous_information_gain = info_gain
                info_gain = compute_information_gain(
                    previous_claims_count=previous_claims_count,
                    current_claims_count=total_claims_count,
                    new_unique_entities=new_nodes,
                    existing_entities=max(0, len(nodes) - new_nodes),
                )
                previous_claims_count = total_claims_count

                # Consecutive low-novelty iterations: the patience counter the
                # stopping policy needs to separate a real plateau from one bad query.
                plateau_iterations = (
                    plateau_iterations + 1
                    if info_gain < NOVELTY_PLATEAU_GAIN
                    else 0
                )

                coverage = compute_coverage_estimate(
                    claims_count=total_claims_count,
                    sources_count=total_sources_count,
                    min_sources_required=session.min_sources_required,
                    depth=session.depth,
                    nodes_count=len(nodes),
                )

                # A verification search is only worth an iteration when the
                # contradiction set changed since the last one.
                contradiction_signature = frozenset(
                    (c.claim_1_id, c.claim_2_id) for c in contradictions
                )
                contradictions_are_new = bool(contradiction_signature) and (
                    contradiction_signature != last_verified_signature
                )

                state = KnowledgeState(
                    iteration=iteration,
                    sources_count=total_sources_count,
                    claims_count=total_claims_count,
                    nodes_count=len(nodes),
                    edges_count=len(edges),
                    unresolved_contradictions=len(contradictions),
                    coverage_estimate=coverage,
                    information_gain=info_gain,
                    previous_information_gain=previous_information_gain,
                    previous_coverage=previous_coverage,
                    new_claims_last_iteration=len(new_claims),
                    new_sources_last_iteration=len(new_sources),
                    new_nodes_last_iteration=new_nodes,
                    plateau_iterations=plateau_iterations,
                    contradictions_are_new=contradictions_are_new,
                    facet_coverage=facet_snapshot.coverage,
                    facet_gaps=list(facet_snapshot.gaps),
                    gaps=gaps,
                    max_iterations=max_iterations,
                    elapsed_time_minutes=(time.time() - start_time) / 60.0,
                    max_research_time_minutes=session.max_research_time_minutes,
                )
                previous_coverage = coverage

                action, reasoning = decision_engine.select_action(state)

                async with async_session_maker() as db:
                    await decision_engine.record_decision(
                        state, action, reasoning, db=db
                    )
                    await db.commit()

                decision_payload: dict[str, Any] = {
                    "type": "decision_made",
                    "action": action.value,
                    "reasoning": reasoning,
                    "coverage": coverage,
                }
                if action == ActionType.STOP:
                    stop_reason = reasoning
                    decision_payload["stop_reason"] = reasoning
                await ws_manager.broadcast(self.session_id, decision_payload)

                usage = llm_router.usage(self.session_id)
                await ws_manager.broadcast(
                    self.session_id,
                    {
                        "type": "iteration_complete",
                        "iteration": iteration,
                        "information_gain": info_gain,
                        "coverage": coverage,
                        # Budget telemetry: how much of this session's model
                        # allowance the iteration spent.
                        "facet_coverage": facet_snapshot.coverage,
                        "evidence": (
                            knowledge_index.evidence_stats if knowledge_index else None
                        ),
                        "versions": (
                            knowledge_index.version_stats if knowledge_index else None
                        ),
                        "temporal_versions_suppressed": temporal_versions_suppressed,
                        "llm_calls": usage["calls"],
                        "budget_calls": usage["max_calls"],
                        "context_chars": usage["context_chars"],
                        "context_budget_chars": usage["max_context_chars"],
                    },
                )

                # ─── V2 2.3 / 2.7 — record the transition and run the shadow ─────
                # Runs after the decision so the transition can say whether the run is
                # terminal, and after the live broadcast so a slow disk never delays
                # what the user sees. Both writes are inside the recorder's own
                # try/except; nothing here can interrupt the research loop.
                recorded = await trajectory_recorder.record_iteration(
                    iteration=iteration,
                    executed_action=executed_action,
                    action_parameters=executed_action_parameters,
                    next_action=action.value,
                    next_action_reasoning=reasoning,
                    information_gain=info_gain,
                    coverage=coverage,
                    new_sources=len(new_sources),
                    new_claims=len(new_claims),
                    new_nodes=new_nodes,
                    new_edges=new_edges,
                    total_sources=total_sources_count,
                    total_claims=total_claims_count,
                    total_nodes=len(nodes),
                    total_edges=len(edges),
                    unresolved_contradictions=len(contradictions),
                    resolved_contradictions=sum(
                        1 for c in contradictions if c.resolved
                    ),
                    gaps=gaps,
                    facet_coverage=facet_snapshot.coverage,
                    source_credibilities=[
                        float(source.credibility_score or 0.5)
                        for source in all_sources
                    ],
                    source_urls=[source.url for source in all_sources],
                    claim_confidences=[claim.confidence for claim in all_claims],
                    duplicate_claim_count=count_duplicate_claims(
                        claim.claim for claim in all_claims
                    ),
                    contradictions_are_new=contradictions_are_new,
                    plateau_iterations=plateau_iterations,
                    duration_seconds=time.time() - iteration_started,
                    elapsed_seconds=time.time() - start_time,
                    llm_calls=usage["calls"],
                    llm_call_budget=usage["max_calls"],
                    queries_executed=search_agent.queries_executed,
                    max_queries=search_agent.max_queries,
                )
                if recorded is not None:
                    await ws_manager.broadcast(
                        self.session_id, recorded.to_event()
                    )
                    if recorded.shadow:
                        await ws_manager.broadcast(
                            self.session_id,
                            {"type": "rl_shadow", **recorded.shadow},
                        )

                # Check if decision was to stop
                if action == ActionType.STOP:
                    logger.info(
                        f"JEV selected STOP for session {self.session_id}: {reasoning}"
                    )
                    break

                # Remember which contradiction set was just verified so the same
                # pairs do not trigger verification again next iteration.
                if action == ActionType.VERIFY:
                    last_verified_signature = contradiction_signature

                # Prepare query for next iteration
                claims_by_id = {claim.id: claim.claim for claim in all_claims}
                previous_action = executed_action
                current_query, current_facet = self._next_query(
                    action=action,
                    gaps=gaps,
                    contradictions=contradictions,
                    claims_by_id=claims_by_id,
                    question=session.question,
                    planner=facet_planner,
                    memory=search_memory,
                    index=knowledge_index,
                )
                # What iteration N+1 will execute is JEV's decision at N, with the
                # query the planner selected for it.
                executed_action = action.value
                executed_action_parameters = {
                    "query": current_query,
                    "facet": current_facet,
                    "previous_action": previous_action,
                }

                # Brief async sleep to prevent thundering herd
                await asyncio.sleep(1.0)

        except SessionBudgetExceededError as e:
            # Running out of call or context budget is a graceful end, not a
            # failure: keep the session alive so the evidence already gathered
            # still becomes a report, and say why it stopped.
            stop_reason = f"Stopped on budget — {e.message}"
            logger.warning(
                f"Session {self.session_id} stopped on LLM budget: {e.message}"
            )
        except Exception as e:
            await self._mark_failed(e)
            return

        # 6. Final Report Compilation. Outside the loop's try block so a budget
        # stop above still produces a report.
        logger.info(
            f"Generating final research report for session {self.session_id}..."
        )
        try:
            async with async_session_maker() as db:
                report = await report_generator.generate_report(db=db)
                await db.commit()
        except Exception as e:
            await self._mark_failed(e)
            return

        usage = llm_router.usage(self.session_id)

        # ─── V2 2.1 — what this run leaves behind ────────────────────────────
        # Runs after the report exists, so a memory failure cannot cost the user a
        # finished investigation. This is the write half of the loop above: the loop
        # reads memory on the way in and this makes the next run's read richer.
        try:
            stored = await self._remember_outcome(
                session=session,
                report=report,
                stop_reason=stop_reason,
                memory=long_term_memory,
                search_memory=search_memory,
                index=knowledge_index,
                resolver=entity_resolver,
                usage=usage,
            )
            if stored:
                await ws_manager.broadcast(
                    self.session_id,
                    {
                        "type": "memory_updated",
                        "stored": stored,
                        "total": sum(stored.values()),
                    },
                )
        except Exception as exc:  # noqa: BLE001 — never fail a finished run on memory
            logger.warning(
                f"Memory persistence failed ({type(exc).__name__}: {exc})."
            )

        await ws_manager.broadcast(
            self.session_id,
            {
                "type": "completed",
                "report_ready": True,
                "stop_reason": stop_reason or "Research loop finished.",
                "total_claims": report.get("metadata", {}).get("total_claims", 0),
                "total_sources": report.get("metadata", {}).get("total_sources", 0),
                "llm_calls": usage["calls"],
                "budget_calls": usage["max_calls"],
                "context_chars": usage["context_chars"],
                "context_budget_chars": usage["max_context_chars"],
            },
        )

    async def _remember_outcome(
        self,
        *,
        session: Any,
        report: dict[str, Any],
        stop_reason: str | None,
        memory: LongTermMemory,
        search_memory: SearchMemory,
        index: KnowledgeIndex | None,
        resolver: EntityResolver,
        usage: dict[str, Any],
    ) -> dict[str, int]:
        """Write everything this finished run should leave behind for the next one.

        Re-reads the session's rows instead of capturing ORM objects from the loop:
        the loop's instances are detached once their session closes, and an early
        ``break`` can leave a name the loop would have assigned unbound.

        Claims and sources are ordered best-first before the per-kind caps apply, so
        what survives is the strongest evidence rather than the first forty rows.
        """
        async with async_session_maker() as db:
            claims = await ClaimRepository(db).get_by_session(self.session_id)
            sources = await SourceRepository(db).get_by_session(self.session_id)
            contradictions = await ContradictionRepository(db).get_by_session(
                self.session_id
            )

        def strength(claim: Any) -> float:
            """How well-corroborated a claim is, falling back to its own confidence.

            ``Claim.confidence`` is a *label* ("high"/"medium"), so it goes through the
            same mapping the evidence scorer uses — casting it directly would raise on
            every claim the index happens not to cover.
            """
            if index is not None:
                score = index.evidence.get(claim.id)
                if score is not None:
                    return score.strength
            return extraction_confidence(claim.confidence)

        ranked_claims = sorted(claims, key=strength, reverse=True)
        ranked_sources = sorted(
            sources, key=lambda source: source.credibility_score or 0.0, reverse=True
        )
        url_by_source_id = {source.id: source.url for source in sources}
        # Facts with more than one observation (moved, restated or conflicting) come
        # first, so a per-run cap truncates single observations long before history.
        # The version layer then decides what is worth keeping: a fact seen once is
        # only versioned when an earlier run already remembered it (V2 2.12).
        version_groups: list[dict[str, Any]] = []
        if index is not None:
            ordered_groups = sorted(
                index.groups,
                key=lambda group: (len(group.versions), len(group.conflicts)),
                reverse=True,
            )
            for group in ordered_groups:
                if not group.versions:
                    continue
                version_groups.append(
                    {
                        "subject": group.subject,
                        "predicate": group.predicate,
                        "versions": [
                            claim_version_from_ikf(
                                version,
                                session_id=self.session_id,
                                sources=[
                                    url
                                    for url in (
                                        url_by_source_id.get(source_id)
                                        for source_id in version.source_ids
                                    )
                                    if url
                                ],
                            )
                            for version in group.versions
                        ],
                    }
                )
        resolved = [
            f"{contradiction.claim_1.claim if contradiction.claim_1 else ''} "
            f"vs {contradiction.claim_2.claim if contradiction.claim_2 else ''}: "
            f"{contradiction.resolution_note or 'resolved'}"
            for contradiction in contradictions
            if contradiction.resolved
        ]

        stats: dict[str, Any] = {
            "sources": len(sources),
            "claims": len(claims),
            "contradictions": len(contradictions),
            "evidence": (index.evidence_stats if index else {}),
            "versions": (index.version_stats if index else {}),
            "llm_calls": usage.get("calls", 0),
            "stop_reason": stop_reason or "",
        }

        counts = await memory.remember_outcome(
            session_id=self.session_id,
            question=session.question,
            summary=str(report.get("executive_summary") or ""),
            stop_reason=stop_reason,
            stats=stats,
            claims=[(claim.claim, round(strength(claim), 4)) for claim in ranked_claims],
            conclusions=[str(item) for item in (report.get("key_findings") or [])],
            entities=resolver.alias_table(),
            sources=[
                (source.url, source.title or "", float(source.credibility_score or 0.5))
                for source in ranked_sources
            ],
            # A query that worked is reusable on the same subject; one that came back
            # empty is not worth paying for twice in two different sessions.
            strategies=[
                (record.query, record.facet, float(record.new_sources))
                for record in search_memory.successful_queries()
            ],
            failed_queries=[
                record.query
                for record in search_memory.dead_end_queries()
                if record.iteration > 0
            ],
            resolved=resolved,
            domain=classify_facet_text(session.question) or None,
            constraints={
                "depth": session.depth,
                "min_sources_required": session.min_sources_required,
                "max_research_time_minutes": session.max_research_time_minutes,
            },
        )

        # Facts that moved or contradict an earlier run are the part of memory that
        # must not be overwritten blindly, so they get the version treatment: every
        # reading kept, each with its own source, date and status.
        try:
            updates = await memory.remember_claim_versions(
                version_groups, session_id=self.session_id, max_groups=25
            )
            counts.update(updates.to_dict())
        except Exception as exc:  # noqa: BLE001 — memory must never break a run
            logger.warning(
                f"Claim versioning failed ({type(exc).__name__}: {exc})."
            )

        # Forgetting runs in the same breath as remembering: a size cap is only real
        # if something enforces it, and this is the moment the store just grew.
        try:
            pruned = await memory.decay_and_prune()
            if pruned.get("removed_decayed") or pruned.get("removed_overflow"):
                logger.info(
                    f"Session {self.session_id} memory pruned: "
                    f"{pruned['removed_decayed']} decayed, "
                    f"{pruned['removed_overflow']} over cap."
                )
        except Exception as exc:  # noqa: BLE001 — pruning is housekeeping, never fatal
            logger.warning(f"Memory pruning skipped ({type(exc).__name__}: {exc}).")

        return counts

    def _next_query(
        self,
        *,
        action: ActionType,
        gaps: list[str],
        contradictions: list[Contradiction],
        claims_by_id: dict[str, str],
        question: str,
        planner: FacetPlanner,
        memory: SearchMemory,
        index: KnowledgeIndex | None = None,
    ) -> tuple[str, str | None]:
        """Choose the next query and the facet it targets.

        Preference order: evidence for an unresolved contradiction (V1 behaviour),
        then the largest useful coverage gap — a dimension with no evidence is
        worth more than a reworded repeat of a search that already ran — then an
        unattempted query proposed by the gap detector, then a generic deepening
        search.
        """
        if action == ActionType.VERIFY and contradictions:
            # Search the claim text: embedding a claim UUID produces a query no
            # search engine can turn into evidence.
            target_id = self._verify_target_id(contradictions, index)
            target_claim = claims_by_id.get(target_id, "")
            verify_query = (
                f"evidence for or against: {target_claim[:180]}"
                if target_claim
                else f"{question} conflicting evidence"
            )
            if not memory.attempted(verify_query):
                return verify_query, None

        facet_query = planner.next_query(preferred=gaps, memory=memory)
        if facet_query is not None:
            return facet_query.query, facet_query.facet

        if action == ActionType.EXPAND_QUERY:
            for gap in gaps:
                clean = gap.strip()
                if clean and not memory.attempted(clean):
                    return clean, classify_facet_text(clean)

        return f"{question} key findings and analysis", None

    @staticmethod
    def _drop_temporal_versions(
        contradictions: list[Contradiction],
        index: KnowledgeIndex | None,
    ) -> tuple[list[Contradiction], int]:
        """Drop contradiction pairs that are really one fact observed at two dates.

        "Market share was 65% (2024)" against "market share is 71% (2026)" counted as a
        contradiction in V1 and could cost a whole verification iteration. Only pairs
        whose values genuinely conflict survive; a group that is *conflicted* keeps
        its pairs, which is the distinction the versioning layer exists to make.
        """
        if index is None or not contradictions:
            return contradictions, 0

        versioned_pairs: set[frozenset[str]] = set()
        for group in index.groups:
            if group.status != "versioned":
                continue
            claim_ids = [version.claim_id for version in group.versions]
            for position, left in enumerate(claim_ids):
                for right in claim_ids[position + 1 :]:
                    versioned_pairs.add(frozenset((left, right)))

        kept = [
            contradiction
            for contradiction in contradictions
            if frozenset((contradiction.claim_1_id, contradiction.claim_2_id))
            not in versioned_pairs
        ]
        return kept, len(contradictions) - len(kept)

    @staticmethod
    def _verify_target_id(
        contradictions: list[Contradiction],
        index: KnowledgeIndex | None,
    ) -> str:
        """Pick which claim of a conflicting pair a verification search should chase.

        Verifying the first pair in the list is arbitrary. The claim worth searching
        for is the one standing on the thinnest evidence, because a new source can
        actually change it; a claim already backed by four independent sources will
        not move. Without an index this falls back to V1's first-pair behaviour.
        """
        first = contradictions[0]
        if index is None:
            return first.claim_1_id

        def strength(claim_id: str) -> float:
            score = index.evidence.get(claim_id)
            return score.strength if score else 0.0

        return (
            first.claim_1_id
            if strength(first.claim_1_id) <= strength(first.claim_2_id)
            else first.claim_2_id
        )

    async def _mark_failed(self, error: Exception) -> None:
        """Persist and broadcast an unrecoverable failure for this session."""
        logger.exception(
            f"Unhandled error in research orchestrator for session {self.session_id}: {error}"
        )
        async with async_session_maker() as db:
            s_repo = SessionRepository(db)
            await s_repo.update_status(
                self.session_id, status="error", error_message=str(error)
            )
            await db.commit()

        await ws_manager.broadcast(
            self.session_id,
            {
                "type": "error",
                "message": f"Research process encountered an error: {error!s}",
                "recoverable": False,
            },
        )


_running_tasks: dict[str, asyncio.Task] = {}


def launch_research_task(session_id: str) -> asyncio.Task | None:
    """Launch the orchestrator as a tracked background task.

    Keeps a strong reference for the task's lifetime (a bare fire-and-forget task
    can be garbage collected mid-run) and refuses duplicate concurrent runs for the
    same session, so double-submits cannot corrupt a session's iteration history.
    """
    existing = _running_tasks.get(session_id)
    if existing is not None and not existing.done():
        logger.warning(
            f"Session {session_id} already has a running research task; ignoring duplicate launch."
        )
        return existing

    task = asyncio.create_task(ResearchOrchestrator(session_id).run())
    _running_tasks[session_id] = task

    def _release(finished: asyncio.Task) -> None:
        if _running_tasks.get(session_id) is finished:
            _running_tasks.pop(session_id, None)

    task.add_done_callback(_release)
    return task
