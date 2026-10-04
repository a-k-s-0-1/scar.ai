"""Database-facing learning services (V2 2.3 – 2.9).

Everything in this package's pure modules works on plain objects; this module is the
only place that touches SQLAlchemy. It owns four concerns:

* **Trajectory** — reading and building datasets from ``research_transitions``.
* **Policy** — training a :class:`~app.services.rl.policy.TabularPolicy` from a dataset
  and persisting/loading it as an ``rl_policy`` row.
* **Shadow** — recording what the policy would have done next to what JEV did, and
  back-filling the reward once the outcome exists.
* **Evaluation** — running the offline comparison and persisting the result slices.

Every entry point used from the live loop is written so that a failure cannot touch the
session: the recorder swallows and logs, and a missing/unreadable policy simply means
"no shadow recommendation this iteration".
"""

from __future__ import annotations

from datetime import timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Claim,
    Contradiction,
    Decision,
    ResearchAction,
    ResearchTransition,
    RLPolicy,
    Source,
    utc_now,
)
from app.database.repository import (
    ClaimRepository,
    ContradictionRepository,
    DecisionRepository,
    EvaluationRepository,
    KnowledgeRepository,
    PolicyRepository,
    PredictionRepository,
    SessionRepository,
    SourceRepository,
    TransitionRepository,
)
from app.services.metrics import compute_coverage_estimate, compute_information_gain
from app.services.rl.dataset import (
    TrajectoryDataset,
    TransitionRecord,
    build_dataset,
)
from app.services.rl.evaluation import EvaluationReport, evaluate
from app.services.rl.policy import (
    ALGORITHM,
    JevPolicy,
    PolicyPrediction,
    TabularPolicy,
)
from app.services.rl.research_state import (
    ResearchState,
    build_research_state,
)
from app.services.rl.rewards import (
    compute_reward_components,
    is_repeated_without_yield,
)
from app.utils.helpers import compute_url_domain
from app.utils.logger import logger

#: Source quality below which a new source counts against the reward.
LOW_QUALITY_CREDIBILITY = 0.4


def to_transition_record(row: ResearchTransition) -> TransitionRecord:
    """Map an ORM transition onto the pure record used for learning."""
    return TransitionRecord(
        id=row.id,
        session_id=row.session_id,
        iteration=row.iteration,
        state_before=row.state_before,
        action=row.action_type,
        action_parameters=row.action_parameters or {},
        observation=row.observation or {},
        reward=float(row.reward or 0.0),
        reward_components=row.reward_components or {},
        information_gain=float(row.information_gain or 0.0),
        coverage_before=float(row.coverage_before or 0.0),
        coverage_after=float(row.coverage_after or 0.0),
        contradictions_before=int(row.contradictions_before or 0),
        contradictions_after=int(row.contradictions_after or 0),
        sources_added=int(row.sources_added or 0),
        claims_added=int(row.claims_added or 0),
        execution_time=float(row.execution_time or 0.0),
        state_after=row.state_after,
        policy_source=row.policy_source or "JEV",
        done=bool(row.done),
        created_at=row.created_at,
    )


class TrajectoryService:
    """Read/write access to recorded transitions and derived datasets."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = TransitionRepository(db)

    async def load_records(
        self, session_ids: list[str] | None = None, limit: int = 5000
    ) -> list[TransitionRecord]:
        rows = await self.repo.list_transitions(session_ids=session_ids, limit=limit)
        return [to_transition_record(row) for row in rows]

    async def build(
        self,
        session_ids: list[str] | None = None,
        *,
        include_incomplete: bool = False,
        only_complete: bool = False,
    ) -> TrajectoryDataset:
        """Build the validated dataset, complete sessions only by default."""
        candidates = session_ids
        if only_complete and not candidates:
            candidates = await self.repo.completed_session_ids()
        records = await self.load_records(candidates)
        return build_dataset(records, include_incomplete=include_incomplete)

    async def backfill_history(
        self,
        session_ids: list[str] | None = None,
        *,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Reconstruct transitions for completed sessions that predate the recorder.

        V1 logged decisions and per-iteration ``research_actions`` (query, sources
        found, claims extracted, information gain, duration) but never joined a
        decision to its outcome, so historical runs contributed nothing to the
        dataset. This reconstructs that join from stored rows:

        * ``research_actions`` supply the per-iteration yield — the same fields the
          live recorder reads off the orchestrator.
        * sources / claims / contradictions carry no iteration column, so each row
          is windowed to the latest action whose ``created_at`` it precedes —
          everything that existed when that action finished.
        * states are rebuilt cumulatively with the same aggregate helpers the
          recorder uses (coverage, quality, diversity, duplicates); what cannot be
          recovered per window (facet gaps, contradiction resolution timing, LLM
          call counts) is left at its neutral value and marked
          ``observation["backfilled"] = True`` so no consumer mistakes it for a
          measured live step.

        Idempotent: a session that already has transitions is skipped. Completed
        sessions only, unless ``session_ids`` says otherwise.
        """
        if session_ids:
            candidates = list(session_ids)
        else:
            # Status-based, not transition-based: historical runs predate
            # transitions entirely, so "has a done transition" can never
            # describe them (that is what completed_session_ids means).
            completed = set(await self.repo.finished_session_ids())
            with_transitions = set(await self.repo.session_ids_with_transitions())
            candidates = sorted(completed - with_transitions)

        created = 0
        skipped: list[str] = []
        touched: list[str] = []
        for session_id in candidates[:limit]:
            existing = await self.repo.get_by_session(session_id)
            if existing:
                skipped.append(session_id)
                continue
            try:
                n = await self._backfill_session(session_id)
            except Exception as exc:  # noqa: BLE001 — one bad session must not stop the backfill
                logger.warning(
                    f"Backfill skipped session {session_id}: {type(exc).__name__}: {exc}"
                )
                skipped.append(session_id)
                continue
            if n:
                created += n
                touched.append(session_id)
                await self.db.commit()

        return {
            "sessions_requested": len(candidates[:limit]),
            "sessions_backfilled": len(touched),
            "transitions_created": created,
            "skipped": len(skipped),
            "session_ids": touched,
        }

    async def _backfill_session(self, session_id: str) -> int:
        """Reconstruct one session's transitions; returns how many were written."""
        session = await SessionRepository(self.db).get_by_id(session_id)
        if session is None:
            return 0

        steps = await self._reconstruct_steps(session)
        if not steps:
            return 0

        sources = sorted(
            await SourceRepository(self.db).get_by_session(session_id),
            key=lambda row: _as_utc(row.created_at) or utc_now(),
        )
        claims = sorted(
            await ClaimRepository(self.db).get_by_session(session_id),
            key=lambda row: _as_utc(row.created_at) or utc_now(),
        )
        contradictions = await ContradictionRepository(self.db).get_by_session(
            session_id
        )
        nodes, edges = await KnowledgeRepository(self.db).get_graph(session_id)
        from app.services.depth_config import get_depth_profile

        max_iterations = get_depth_profile(session.depth).max_iterations
        resolved_total = sum(1 for item in contradictions if item.resolved)

        seen_domains: set[str] = set()
        seen_claim_keys: set[str] = set()
        previous_reward: float | None = None
        previous_action: str | None = None
        written = 0
        last_index = len(steps) - 1

        for index, step in enumerate(steps):
            before_cut = step["before_cut"]
            after_cut = step["after_cut"]

            win_sources = [
                s for s in sources
                if (before_cut is None or _as_utc(s.created_at) > before_cut)
                and (after_cut is None or _as_utc(s.created_at) <= after_cut)
            ]
            win_claims = [
                c for c in claims
                if (before_cut is None or _as_utc(c.created_at) > before_cut)
                and (after_cut is None or _as_utc(c.created_at) <= after_cut)
            ]
            cum_sources = [
                s for s in sources
                if after_cut is None or _as_utc(s.created_at) <= after_cut
            ]
            cum_claims = [
                c for c in claims
                if after_cut is None or _as_utc(c.created_at) <= after_cut
            ]

            # Per-window observables.
            win_domains: set[str] = set()
            for source in win_sources:
                domain = compute_url_domain(source.url) if source.url else None
                if domain and domain not in seen_domains:
                    seen_domains.add(domain)
                    win_domains.add(domain)
            new_domains = len(win_domains)

            duplicate_findings = 0
            for claim in win_claims:
                key = " ".join((claim.claim or "").lower().split())
                if key in seen_claim_keys:
                    duplicate_findings += 1
                seen_claim_keys.add(key)
            low_quality_sources = sum(
                1
                for s in win_sources
                if float(s.credibility_score or 0.5) < LOW_QUALITY_CREDIBILITY
            )

            # Cumulative aggregates for the two states. A None before_cut means
            # "nothing exists yet" (the initial search's before-state), NOT
            # "everything" — the empty corpus is what makes the first step's
            # coverage 0 and lets a replayed JEV see the run the way it saw it.
            if before_cut is not None:
                before_sources = [
                    s for s in sources if _as_utc(s.created_at) <= before_cut
                ]
                before_claims = [
                    c for c in claims if _as_utc(c.created_at) <= before_cut
                ]
            else:
                before_sources, before_claims = [], []
            before_agg = self._cumulative_aggregates(
                sources=before_sources,
                claims=before_claims,
                contradictions=contradictions,
                resolved_total=resolved_total,
                session=session,
                as_of=before_cut if before_cut is not None else session.started_at,
            )
            after_agg = self._cumulative_aggregates(
                sources=cum_sources,
                claims=cum_claims,
                contradictions=contradictions,
                resolved_total=resolved_total,
                session=session,
                as_of=after_cut,
            )

            measured_gain = step["information_gain"]
            information_gain = (
                float(measured_gain)
                if measured_gain is not None
                else compute_information_gain(
                    previous_claims_count=before_agg["total_claims"],
                    current_claims_count=after_agg["total_claims"],
                    new_unique_entities=0,
                    existing_entities=len(nodes),
                )
            )
            coverage_before = compute_coverage_estimate(
                claims_count=before_agg["total_claims"],
                sources_count=before_agg["total_sources"],
                min_sources_required=session.min_sources_required,
                depth=session.depth,
                nodes_count=len(nodes) if before_agg["total_claims"] else 0,
            )
            coverage_after = compute_coverage_estimate(
                claims_count=after_agg["total_claims"],
                sources_count=after_agg["total_sources"],
                min_sources_required=session.min_sources_required,
                depth=session.depth,
                nodes_count=len(nodes) if after_agg["total_claims"] else 0,
            )

            state_before = build_research_state(
                session_id=session_id,
                question=session.question,
                iteration=max(0, step["iteration"] - 1),
                depth=session.depth,
                max_iterations=max_iterations,
                total_sources=before_agg["total_sources"],
                total_claims=before_agg["total_claims"],
                total_nodes=len(nodes),
                total_edges=len(edges),
                information_gain=0.0,
                coverage=coverage_before,
                unresolved_contradictions=before_agg["unresolved"],
                resolved_contradictions=before_agg["resolved"],
                gaps=[],
                source_quality=before_agg["quality"],
                source_diversity=before_agg["diversity"],
                confidence_distribution=before_agg["confidence"],
                duplicate_count=before_agg["duplicates"],
                time_elapsed=before_agg["elapsed"],
                remaining_time=before_agg["remaining"],
                previous_action=previous_action,
                previous_reward=previous_reward,
            )
            state_after = build_research_state(
                session_id=session_id,
                question=session.question,
                iteration=step["iteration"],
                depth=session.depth,
                max_iterations=max_iterations,
                total_sources=after_agg["total_sources"],
                total_claims=after_agg["total_claims"],
                total_nodes=len(nodes),
                total_edges=len(edges),
                information_gain=information_gain,
                coverage=coverage_after,
                unresolved_contradictions=after_agg["unresolved"],
                resolved_contradictions=after_agg["resolved"],
                gaps=[],
                source_quality=after_agg["quality"],
                source_diversity=after_agg["diversity"],
                confidence_distribution=after_agg["confidence"],
                duplicate_count=after_agg["duplicates"],
                time_elapsed=after_agg["elapsed"],
                remaining_time=after_agg["remaining"],
                previous_action=step["action_type"],
                previous_reward=None,
                current_query=step["query"],
            )

            components = compute_reward_components(
                information_gain=information_gain,
                avg_credibility=after_agg["quality"],
                coverage_before=coverage_before,
                coverage_after=coverage_after,
                unresolved_contradictions=after_agg["unresolved"],
                resolved_contradictions=0,  # resolution timing is not recoverable
                new_domains=new_domains,
                duplicate_findings=duplicate_findings,
                new_sources=step["sources_found"],
                low_quality_sources=low_quality_sources,
                repeated_action_without_yield=is_repeated_without_yield(
                    action=step["action_type"],
                    previous_action=previous_action,
                    information_gain=information_gain,
                    new_sources=step["sources_found"],
                    new_claims=step["claims_added"],
                ),
                duration_seconds=step["duration_seconds"],
                llm_calls=0,
                llm_call_budget=0,
            )

            action_type = step["action_type"].upper()
            is_stop = action_type == "STOP"
            await self.repo.upsert(
                session_id=session_id,
                iteration=step["iteration"],
                state_before=state_before.to_dict(),
                state_after=state_after.to_dict(),
                action_type=action_type,
                action_parameters={"query": step["query"]} if step["query"] else {},
                observation={
                    "query": step["query"],
                    "facet": None,
                    "sources_added": step["sources_found"],
                    "claims_added": step["claims_added"],
                    "nodes_added": 0,
                    "edges_added": 0,
                    "new_domains": new_domains,
                    "contradictions_found": 0,
                    "contradictions_resolved": 0,
                    "gaps_found": [],
                    "duplicate_claims": duplicate_findings,
                    "low_quality_sources": low_quality_sources,
                    "llm_calls": 0,
                    "backfilled": True,
                    "reconstructed_from": step["reconstructed_from"],
                },
                reward=components.total,
                reward_components=components.to_dict(),
                information_gain=information_gain,
                coverage_before=coverage_before,
                coverage_after=coverage_after,
                contradictions_before=before_agg["unresolved"],
                contradictions_after=after_agg["unresolved"],
                sources_added=step["sources_found"],
                claims_added=step["claims_added"],
                execution_time=step["duration_seconds"],
                policy_source="JEV",
                done=is_stop or index == last_index,
                state_hash=state_after.state_hash(),
                state_bytes=state_after.state_size(),
            )
            written += 1
            previous_action = step["action_type"]
            previous_reward = components.total

        await self.db.commit()
        if written:
            logger.info(
                f"Backfilled {written} transition(s) for session {session_id}."
            )
        return written

    async def _reconstruct_steps(self, session: Any) -> list[dict[str, Any]]:
        """Normalized iteration steps from research_actions or, failing that, decisions.

        Two historical layouts exist. Runs that logged ``research_actions`` carry the
        per-iteration yield directly. Older runs logged only ``decisions``; there the
        work between consecutive decision timestamps is the outcome of the earlier
        decision's action, and the rows that exist before the first decision are the
        outcome of V1's unconditional initial search (a synthetic iteration-0 step).
        """
        session_id = session.id
        result = await self.db.execute(
            select(ResearchAction)
            .where(ResearchAction.session_id == session_id)
            .order_by(
                ResearchAction.iteration_number.asc(), ResearchAction.created_at.asc()
            )
        )
        actions = list(result.scalars().all())

        if actions:
            steps: list[dict[str, Any]] = []
            prev_cut = None
            for action in actions:
                steps.append(
                    {
                        "iteration": action.iteration_number,
                        "action_type": (action.action_type or "SEARCH").upper(),
                        "query": action.query,
                        "before_cut": prev_cut,
                        "after_cut": _as_utc(action.created_at),
                        "sources_found": int(action.sources_found or 0),
                        "claims_added": int(action.new_claims_extracted or 0),
                        "information_gain": action.information_gain,
                        "duration_seconds": float(action.duration_seconds or 0),
                        "reconstructed_from": "research_actions",
                    }
                )
                prev_cut = _as_utc(action.created_at)
            return steps

        decisions = await DecisionRepository(self.db).get_by_session(session_id)
        chosen = [
            d for d in decisions
            if d.selected_action and _as_utc(d.created_at) is not None
        ]
        if not chosen:
            return []

        # One decision per iteration: the first logged for it wins.
        by_iteration: dict[int, Any] = {}
        for decision in chosen:
            by_iteration.setdefault(decision.iteration_number, decision)
        ordered = sorted(
            by_iteration.values(),
            key=lambda d: (_as_utc(d.created_at), d.iteration_number),
        )

        session_end = _as_utc(session.completed_at) or utc_now()
        sources = await SourceRepository(self.db).get_by_session(session_id)
        claims = await ClaimRepository(self.db).get_by_session(session_id)
        first_decision_cut = _as_utc(ordered[0].created_at)

        def _in_window(rows: list[Any], lo: Any, hi: Any) -> int:
            return sum(
                1
                for row in rows
                if (stamp := _as_utc(row.created_at)) is not None
                and (lo is None or stamp > lo)
                and (hi is None or stamp <= hi)
            )

        steps: list[dict[str, Any]] = []
        # V1 performed an unconditional initial search before the first JEV
        # decision; rows older than that decision are its outcome, and that search
        # *is* iteration 1. Every later decision k was made at the end of iteration
        # k and selected the action that ran during iteration k+1, so the decision
        # steps are shifted by one; a terminal STOP is not an executed action and
        # instead marks the preceding step as the session's last.
        has_initial_work = (
            _in_window(sources, None, first_decision_cut) > 0
            or _in_window(claims, None, first_decision_cut) > 0
        )
        shift = 1 if has_initial_work else 0
        if has_initial_work:
            duration = (
                max(
                    0.0,
                    (first_decision_cut - _as_utc(session.started_at)).total_seconds(),
                )
                if session.started_at
                else 0.0
            )
            steps.append(
                {
                    "iteration": 1,
                    "action_type": "SEARCH",
                    "query": None,
                    "before_cut": None,
                    "after_cut": first_decision_cut,
                    "sources_found": _in_window(sources, None, first_decision_cut),
                    "claims_added": _in_window(claims, None, first_decision_cut),
                    "information_gain": None,
                    "duration_seconds": duration,
                    "reconstructed_from": "initial_search",
                }
            )

        for position, decision in enumerate(ordered):
            action = (decision.selected_action or "SEARCH").upper()
            if action == "STOP":
                # The loop ended on this decision; it executed nothing. It only
                # makes the step before it terminal, which the unified loop's
                # last-index rule already does.
                continue
            before_cut = _as_utc(decision.created_at)
            after_cut = (
                _as_utc(ordered[position + 1].created_at)
                if position + 1 < len(ordered)
                else session_end
            )
            duration = (
                max(0.0, (after_cut - before_cut).total_seconds())
                if after_cut and before_cut
                else 0.0
            )
            steps.append(
                {
                    "iteration": decision.iteration_number + shift,
                    "action_type": action,
                    "query": None,
                    "before_cut": before_cut,
                    "after_cut": after_cut,
                    "sources_found": _in_window(sources, before_cut, after_cut),
                    "claims_added": _in_window(claims, before_cut, after_cut),
                    "information_gain": None,
                    "duration_seconds": duration,
                    "reconstructed_from": "decisions",
                }
            )
        return steps

    def _cumulative_aggregates(
        self,
        *,
        sources: list[Source],
        claims: list[Claim],
        contradictions: list[Contradiction],
        resolved_total: int,
        session: Any,
        as_of: Any = None,
    ) -> dict[str, Any]:
        """Aggregate helpers for a cumulative row window (same maths as live)."""
        quality = (
            sum(float(s.credibility_score or 0.5) for s in sources) / len(sources)
            if sources
            else 0.0
        )
        diversity = len(
            {compute_url_domain(s.url) for s in sources if s.url}
        )
        confidence: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        seen: set[str] = set()
        duplicates = 0
        for claim in claims:
            label = (claim.confidence or "medium").lower()
            confidence[label] = confidence.get(label, 0) + 1
            key = " ".join((claim.claim or "").lower().split())
            if key in seen:
                duplicates += 1
            seen.add(key)
        # Time as the run saw it: elapsed from the session's start to this
        # cumulative cut, remaining against the configured cap. Leaving these at
        # zero would make a replayed JEV read "out of time" and stop instantly —
        # the replay must see the budget pressure the live run saw.
        started = _as_utc(session.started_at)
        as_of_utc = _as_utc(as_of)
        elapsed = (
            max(0.0, (as_of_utc - started).total_seconds())
            if started and as_of_utc
            else 0.0
        )
        cap_seconds = float(session.max_research_time_minutes or 0) * 60.0
        remaining = max(0.0, cap_seconds - elapsed) if cap_seconds else 0.0
        return {
            "total_sources": len(sources),
            "total_claims": len(claims),
            "quality": round(quality, 4),
            "diversity": diversity,
            "confidence": confidence,
            "duplicates": duplicates,
            "unresolved": max(0, len(contradictions) - resolved_total),
            "resolved": resolved_total,
            "elapsed": round(elapsed, 2),
            "remaining": round(remaining, 2),
        }

    async def session_trajectory(self, session_id: str) -> list[TransitionRecord]:
        rows = await self.repo.get_by_session(session_id)
        return [to_transition_record(row) for row in rows]

    async def stats(self) -> dict[str, Any]:
        """Dataset-level stats over everything recorded, without training anything."""
        dataset = await self.build(include_incomplete=True)
        counts = await self.dataset_stats_by_source()
        stats = dataset.stats()
        stats["recorded_transitions"] = await self.repo.count()
        stats["sessions_with_transitions"] = len(
            await self.repo.session_ids_with_transitions()
        )
        stats["complete_sessions"] = len(await self.repo.completed_session_ids())
        stats["by_policy_source"] = counts
        return stats

    async def dataset_stats_by_source(self) -> dict[str, int]:
        records = await self.load_records()
        counts: dict[str, int] = {}
        for record in records:
            counts[record.policy_source] = counts.get(record.policy_source, 0) + 1
        return counts


class PolicyService:
    """Train, persist and load the offline policy."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = PolicyRepository(db)
        self.trajectories = TrajectoryService(db)

    async def train(
        self,
        *,
        session_ids: list[str] | None = None,
        include_incomplete: bool = False,
        shrinkage: float | None = None,
        min_samples: int | None = None,
        name: str = "jev-baseline-shadow",
        activate: bool = True,
    ) -> tuple[RLPolicy | None, TrajectoryDataset, TabularPolicy | None]:
        """Train on the current dataset and store the result as a new policy row."""
        dataset = await self.trajectories.build(
            session_ids, include_incomplete=include_incomplete
        )
        if not dataset.records:
            logger.info("RL policy training skipped: the dataset is empty.")
            return None, dataset, None

        from app.config import get_settings

        settings = get_settings()
        policy = TabularPolicy.train(
            dataset.records,
            shrinkage=(
                shrinkage
                if shrinkage is not None
                else settings.RL_POLICY_SHRINKAGE
            ),
            min_samples=(
                min_samples if min_samples is not None else settings.RL_POLICY_MIN_SAMPLES
            ),
            dataset_version=dataset.version,
            dataset_hash=dataset.dataset_hash(),
        )
        record = await self.repo.create(
            name=name,
            algorithm=ALGORITHM,
            version="1.0",
            payload=policy.to_dict(),
            dataset_version=dataset.version,
            dataset_hash=dataset.dataset_hash(),
            baseline="JEV",
            samples=policy.samples,
            sessions=len(dataset.sessions),
            metrics=policy.describe(),
            notes=(
                "Offline tabular policy trained from recorded JEV trajectories. "
                "Used for shadow predictions and evaluation only; JEV remains the "
                "production decision maker."
            ),
            active=activate,
        )
        if activate:
            await self.repo.set_active(record.id)
            record = await self.repo.get_by_id(record.id) or record
        logger.info(
            f"Trained RL policy {record.id} on {policy.samples} transition(s) from "
            f"{len(dataset.sessions)} session(s)."
        )
        return record, dataset, policy

    async def active_policy(self) -> TabularPolicy | None:
        """The active policy, or ``None`` when there is nothing usable to load.

        A missing or unreadable payload is normal (fresh database, older rows) and must
        never raise on the research path — the loop simply runs without shadow data.
        """
        row = await self.repo.get_active()
        if row is None:
            return None
        policy = TabularPolicy.from_dict(row.payload)
        if policy is None:
            logger.warning(
                f"Active policy {row.id} has an unrecognised payload; ignoring it."
            )
        return policy

    async def active_policy_row(self) -> RLPolicy | None:
        return await self.repo.get_active()

    async def list_policies(self, limit: int = 50) -> list[RLPolicy]:
        return await self.repo.list_policies(limit=limit)

    async def activate(self, policy_id: str) -> RLPolicy | None:
        return await self.repo.set_active(policy_id)


class ShadowService:
    """Record the policy's recommendation beside JEV's, without executing it."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = PredictionRepository(db)
        self.policies = PolicyService(db)

    async def predict(
        self,
        state: ResearchState,
        *,
        available_actions: list[str] | None = None,
    ) -> tuple[PolicyPrediction | None, RLPolicy | None]:
        policy = await self.policies.active_policy()
        if policy is None:
            return None, None
        prediction = policy.predict(state, available_actions)
        return prediction, await self.policies.active_policy_row()

    async def record(
        self,
        *,
        session_id: str,
        iteration: int,
        state: ResearchState,
        jev_action: str,
        jev_reasoning: str | None,
        prediction: PolicyPrediction,
        policy_id: str | None,
        jev_expected_value: float | None = None,
        actual_reward: float | None = None,
    ) -> Any:
        row = await self.repo.create(
            session_id=session_id,
            iteration=iteration,
            policy_id=policy_id,
            state_key=state.state_key(),
            state=state.to_dict(),
            jev_action=jev_action,
            jev_reasoning=(jev_reasoning or "")[:2000],
            jev_expected_value=jev_expected_value,
            rl_action=prediction.action,
            rl_expected_value=prediction.expected_value,
            rl_scores=prediction.scores,
            rl_support=prediction.support_total,
            fallback=prediction.fallback,
            estimated_rl_reward=prediction.expected_value,
            disagreement=prediction.action.upper() != jev_action.upper(),
        )
        if actual_reward is not None:
            await self.repo.update_reward(row.id, actual_reward)
        return row

    async def backfill_reward(self, session_id: str, iteration: int, reward: float) -> None:
        """Attach the JEV action's measured reward to the prediction that preceded it."""
        rows = await self.repo.get_by_session(session_id, limit=500)
        for row in rows:
            if row.iteration == iteration and row.actual_reward is None:
                await self.repo.update_reward(row.id, reward)
                return

    async def session_predictions(self, session_id: str) -> list[Any]:
        return await self.repo.get_by_session(session_id)

    async def agreement_stats(self) -> dict[str, int]:
        return await self.repo.agreement_stats()


class EvaluationService:
    """Run the offline JEV-vs-RL comparison and persist its slices."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = EvaluationRepository(db)
        self.trajectories = TrajectoryService(db)
        self.policies = PolicyService(db)

    async def run(
        self,
        *,
        policy: str = "rl",
        baseline: str = "jev",
        dataset_version: str | None = None,
        session_ids: list[str] | None = None,
        max_steps: int | None = None,
        include_incomplete: bool = False,
        persist: bool = True,
    ) -> EvaluationReport:
        """Evaluate one policy (optionally against JEV) over the stored dataset.

        ``dataset_version`` is accepted so a caller can pin an evaluation to the data
        it was trained on; an unsupported value is reported by the caller rather than
        silently ignored here.
        """
        dataset = await self.trajectories.build(
            session_ids, include_incomplete=include_incomplete
        )
        baseline_policy = JevPolicy() if baseline == "jev" else None

        if policy == "jev":
            report = evaluate(dataset, JevPolicy(), baseline=None, max_steps=max_steps)
        else:
            learned = await self.policies.active_policy()
            if learned is None:
                logger.info(
                    "RL evaluation requested but no active policy exists; "
                    "evaluating JEV instead."
                )
                report = evaluate(
                    dataset, JevPolicy(), baseline=None, max_steps=max_steps
                )
                report.notes.append(
                    "No trained policy is active, so this run evaluates JEV. "
                    "Build a dataset and train a policy first."
                )
            else:
                report = evaluate(
                    dataset, learned, baseline=baseline_policy, max_steps=max_steps
                )
        report.dataset_version = dataset_version or report.dataset_version

        if persist and report.dataset_size:
            await self._persist(
                report,
                config={
                    "policy": policy,
                    "baseline": baseline,
                    "dataset_version": dataset_version,
                    "max_steps": max_steps,
                    "include_incomplete": include_incomplete,
                },
            )
        return report

    async def _persist(self, report: EvaluationReport, config: dict[str, Any]) -> Any:
        run = await self.repo.create_run(
            policy=report.policy,
            baseline=report.baseline,
            dataset_version=report.dataset_version,
            dataset_hash=report.dataset_hash,
            dataset_size=report.dataset_size,
            sessions=len(report.sessions),
            max_steps=report.max_steps,
            status="completed",
            config=config,
            aggregate=report.metrics.to_dict(),
            comparison=report.comparison,
            notes=report.notes,
        )
        await self.repo.add_result(
            run.id,
            scope="overall",
            key=report.policy,
            sample_size=report.metrics.steps,
            metrics=report.metrics.to_dict(),
        )
        for row in report.per_session:
            await self.repo.add_result(
                run.id,
                scope="session",
                key=str(row["session_id"]),
                sample_size=int(row["steps"]),
                metrics=row,
            )
        for row in report.per_action:
            await self.repo.add_result(
                run.id,
                scope="action",
                key=str(row["action"]),
                sample_size=int(row["sample_size"]),
                metrics=row,
            )
        await self.db.flush()
        return run

    async def list_runs(self, limit: int = 20) -> list[Any]:
        return await self.repo.list_runs(limit=limit)

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        run = await self.repo.get_run(run_id)
        if run is None:
            return None
        results = await self.repo.list_results(run_id)
        return {
            "id": run.id,
            "policy": run.policy,
            "baseline": run.baseline,
            "dataset_version": run.dataset_version,
            "dataset_hash": run.dataset_hash,
            "dataset_size": run.dataset_size,
            "sessions": run.sessions,
            "max_steps": run.max_steps,
            "status": run.status,
            "config": run.config or {},
            "aggregate": run.aggregate or {},
            "comparison": run.comparison or {},
            "notes": run.notes or [],
            "created_at": run.created_at,
            "completed_at": run.completed_at,
            "results": [
                {
                    "scope": result.scope,
                    "key": result.key,
                    "sample_size": result.sample_size,
                    "metrics": result.metrics,
                }
                for result in results
            ],
        }


async def build_state_from_db(
    session_id: str, db: AsyncSession
) -> ResearchState | None:
    """Reconstruct the current research state from stored rows.

    Used by ``GET /api/research/{id}/state`` for runs that have no recorded transition
    yet (or predate trajectory recording). Reads the same aggregates the recorder uses:
    counts, means and domains, never source content.
    """
    session = await SessionRepository(db).get_by_id(session_id)
    if session is None:
        return None

    transitions = await TransitionRepository(db).get_by_session(session_id)
    if transitions:
        latest = transitions[-1]
        if latest.state_after:
            state = ResearchState.from_dict(latest.state_after)
            # The stored state is authoritative; only the query (which belongs to the
            # *next* step) is taken from the live row.
            return state

    sources = await SourceRepository(db).get_by_session(session_id)
    claims = await ClaimRepository(db).get_by_session(session_id)
    nodes, edges = await KnowledgeRepository(db).get_graph(session_id)
    contradictions = await ContradictionRepository(db).get_by_session(session_id)
    decisions = await DecisionRepository(db).get_by_session(session_id)

    resolved = sum(1 for item in contradictions if item.resolved)
    quality = (
        sum(float(source.credibility_score or 0.5) for source in sources) / len(sources)
        if sources
        else 0.0
    )
    domains = {compute_url_domain(source.url) for source in sources if source.url}
    confidence_distribution: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    seen_claims: set[str] = set()
    duplicates = 0
    for claim in claims:
        label = (claim.confidence or "medium").lower()
        confidence_distribution[label] = confidence_distribution.get(label, 0) + 1
        key = " ".join((claim.claim or "").lower().split())
        if key in seen_claims:
            duplicates += 1
        seen_claims.add(key)

    from app.services.metrics import compute_coverage_estimate, compute_information_gain

    coverage = compute_coverage_estimate(
        claims_count=len(claims),
        sources_count=len(sources),
        min_sources_required=session.min_sources_required,
        depth=session.depth,
        nodes_count=len(nodes),
    )
    # Without a recorded transition there is no measured per-iteration yield; the
    # corpus itself is the best available signal, and it is labelled as such.
    information_gain = compute_information_gain(
        previous_claims_count=max(0, len(claims) - 1),
        current_claims_count=len(claims),
        new_unique_entities=0,
        existing_entities=len(nodes),
    )
    elapsed = _elapsed_seconds(session.started_at, session.completed_at)
    remaining_time = max(0.0, session.max_research_time_minutes * 60 - elapsed)

    return build_research_state(
        session_id=session.id,
        question=session.question,
        iteration=session.current_iteration,
        depth=session.depth,
        max_iterations=session.current_iteration,
        total_sources=len(sources),
        total_claims=len(claims),
        total_nodes=len(nodes),
        total_edges=len(edges),
        information_gain=information_gain,
        coverage=coverage,
        unresolved_contradictions=len(contradictions) - resolved,
        resolved_contradictions=resolved,
        gaps=[],
        source_quality=round(quality, 4),
        source_diversity=len(domains),
        confidence_distribution=confidence_distribution,
        duplicate_count=duplicates,
        time_elapsed=elapsed,
        remaining_time=remaining_time,
        previous_action=decisions[-1].selected_action if decisions else None,
    )


def _as_utc(value: Any) -> Any:
    """Read a SQLite datetime as UTC, whether it came back naive or aware."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _elapsed_seconds(started_at: Any, completed_at: Any) -> float:
    """Seconds between two timestamps, tolerating SQLite's naive datetimes.

    SQLite stores ``TIMESTAMP`` without a zone and hands it back naive, while
    ``utc_now()`` is aware; subtracting them raises. Both are UTC in this application,
    so a missing zone is read as UTC rather than guessed.
    """
    if started_at is None:
        return 0.0
    start = (
        started_at
        if started_at.tzinfo is not None
        else started_at.replace(tzinfo=timezone.utc)
    )
    if completed_at is None:
        end = utc_now()
    else:
        end = (
            completed_at
            if completed_at.tzinfo is not None
            else completed_at.replace(tzinfo=timezone.utc)
        )
    return max(0.0, (end - start).total_seconds())


def decision_to_dict(decision: Decision) -> dict[str, Any]:
    """API shape for one stored JEV decision."""
    return {
        "id": decision.id,
        "iteration": decision.iteration_number,
        "selected_action": decision.selected_action,
        "available_actions": decision.available_actions or [],
        "reasoning": decision.action_reasoning or "",
        "reward_signal": decision.reward_signal,
        "state": decision.knowledge_state_snapshot or {},
        "created_at": decision.created_at,
    }
