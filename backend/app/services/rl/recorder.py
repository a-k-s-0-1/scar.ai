"""Live trajectory recorder and RL shadow (V2 2.3 / 2.7).

This is the only piece of the learning stack the research loop calls. Its contract is
narrow and absolute: **it must never break a run and it must never execute a learned
decision.**

Each iteration it:

1. builds the formal :class:`ResearchState` after the iteration (counts, means, gaps —
   never source content),
2. computes the named reward components from the transition that just happened,
3. persists ``state_before -> action -> observation -> reward -> state_after``,
4. asks the active offline policy what it *would* have done next and stores that beside
   JEV's actual choice — the prediction is recorded, never executed,
5. back-fills the measured reward of the previous JEV action onto its prediction, so
   "JEV said VERIFY, RL said SEARCH, the VERIFY earned +1.8" becomes queryable.

The recorder is deliberately constructed with plain data (question, depth, budgets)
rather than ORM objects, so it can be unit-tested without a session and cannot hold a
detached instance across iterations.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from app.database.repository import PredictionRepository, TransitionRepository
from app.database.session import async_session_maker
from app.services.rl.actions import executable_actions, is_stop
from app.services.rl.policy import JevPolicy, PolicyPrediction, TabularPolicy
from app.services.rl.research_state import (
    ResearchState,
    StateObservation,
    build_research_state,
)
from app.services.rl.rewards import (
    RewardComponents,
    compute_reward_components,
    is_repeated_without_yield,
)
from app.utils.helpers import compute_url_domain
from app.utils.logger import logger

#: Indirection so tests can bind the recorder to their own database engine.
_session_factory: Any = async_session_maker


def set_session_factory(factory: Any) -> None:
    global _session_factory
    _session_factory = factory


def count_duplicate_claims(claim_texts: Iterable[str]) -> int:
    """How many claims in the corpus restate an earlier one.

    Normalised (case and whitespace folded) because "Solar costs fell 90 %" and
    "solar costs fell 90%" are the same finding paid for twice. Deterministic and
    database-free, so the reward term behind it is testable.
    """
    seen: set[str] = set()
    duplicates = 0
    for text in claim_texts:
        key = " ".join((text or "").lower().split())
        if not key:
            continue
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
    return duplicates


@dataclass
class RecordedStep:
    """What the recorder persisted for one iteration, for logging and broadcasting."""

    transition_id: str
    iteration: int
    reward: float
    components: RewardComponents
    observation: dict[str, Any] = field(default_factory=dict)
    state_hash: str = ""
    state_bytes: int = 0
    policy_source: str = "JEV"
    shadow: dict[str, Any] | None = None

    def to_event(self) -> dict[str, Any]:
        """Payload for the WebSocket/durable event stream."""
        return {
            "type": "transition_recorded",
            "iteration": self.iteration,
            "transition_id": self.transition_id,
            "action": self.observation.get("action"),
            "reward": round(self.reward, 4),
            "reward_components": self.components.to_dict(),
            "state_hash": self.state_hash[:12],
            "state_bytes": self.state_bytes,
            "information_gain": self.observation.get("information_gain"),
            "sources_added": self.observation.get("sources_added"),
            "claims_added": self.observation.get("claims_added"),
        }


class TrajectoryRecorder:
    """Persists one transition per iteration and the shadow comparison with it."""

    def __init__(
        self,
        session_id: str,
        *,
        question: str,
        depth: str,
        max_iterations: int,
        min_sources_required: int,
        max_research_time_minutes: int,
        enabled: bool = True,
        shadow_enabled: bool = True,
    ) -> None:
        self.session_id = session_id
        self.question = question
        self.depth = depth
        self.max_iterations = max_iterations
        self.min_sources_required = min_sources_required
        self.max_research_time_minutes = max_research_time_minutes
        self.enabled = enabled
        self.shadow_enabled = shadow_enabled

        self._state_before = build_research_state(
            session_id=session_id,
            question=question,
            iteration=0,
            depth=depth,
            max_iterations=max_iterations,
            remaining_time=max_research_time_minutes * 60,
        )
        self._seen_domains: set[str] = set()
        self._last_action: str | None = None
        self._last_reward: float | None = None
        self._last_prediction_id: str | None = None
        self._policy: TabularPolicy | None = None
        self._policy_id: str | None = None
        self._policy_loaded = False

    # ─── policy loading (once per run, never fatal) ──────────────────────────
    async def _load_policy(self) -> None:
        if self._policy_loaded:
            return
        self._policy_loaded = True
        try:
            async with _session_factory() as db:
                from app.database.repository import PolicyRepository

                row = await PolicyRepository(db).get_active()
                if row is None:
                    return
                policy = TabularPolicy.from_dict(row.payload)
                if policy is None:
                    logger.warning(
                        f"Active RL policy {row.id} has an unrecognised payload; "
                        f"shadow predictions disabled for this run."
                    )
                    return
                self._policy = policy
                self._policy_id = row.id
        except Exception as exc:  # noqa: BLE001 — shadow must never break a run
            logger.warning(
                f"Could not load the offline policy ({type(exc).__name__}: {exc}); "
                f"continuing without shadow predictions."
            )

    @property
    def state_before(self) -> ResearchState:
        """The state this run's next action will be taken from."""
        return self._state_before

    # ─── the per-iteration entry point ───────────────────────────────────────
    async def record_iteration(
        self,
        *,
        iteration: int,
        executed_action: str,
        action_parameters: dict[str, Any],
        next_action: str,
        next_action_reasoning: str,
        information_gain: float,
        coverage: float,
        new_sources: int,
        new_claims: int,
        new_nodes: int,
        new_edges: int,
        total_sources: int,
        total_claims: int,
        total_nodes: int,
        total_edges: int,
        unresolved_contradictions: int,
        resolved_contradictions: int,
        gaps: list[str],
        facet_coverage: float,
        source_credibilities: list[float],
        source_urls: list[str],
        claim_confidences: list[str],
        duplicate_claim_count: int,
        contradictions_are_new: bool,
        plateau_iterations: int,
        duration_seconds: float,
        elapsed_seconds: float,
        llm_calls: int,
        llm_call_budget: int,
        queries_executed: int,
        max_queries: int,
    ) -> RecordedStep | None:
        """Persist one transition and its shadow prediction. Never raises.

        ``executed_action`` is the action this iteration *ran* (JEV's choice from the
        previous iteration, or SEARCH on the first); ``next_action`` is JEV's decision
        for the following iteration, used to mark the episode terminal and to anchor
        the shadow comparison.
        """
        if not self.enabled:
            return None

        try:
            return await self._record(
                iteration=iteration,
                executed_action=executed_action,
                action_parameters=action_parameters,
                next_action=next_action,
                next_action_reasoning=next_action_reasoning,
                information_gain=information_gain,
                coverage=coverage,
                new_sources=new_sources,
                new_claims=new_claims,
                new_nodes=new_nodes,
                new_edges=new_edges,
                total_sources=total_sources,
                total_claims=total_claims,
                total_nodes=total_nodes,
                total_edges=total_edges,
                unresolved_contradictions=unresolved_contradictions,
                resolved_contradictions=resolved_contradictions,
                gaps=gaps,
                facet_coverage=facet_coverage,
                source_credibilities=source_credibilities,
                source_urls=source_urls,
                claim_confidences=claim_confidences,
                duplicate_claim_count=duplicate_claim_count,
                contradictions_are_new=contradictions_are_new,
                plateau_iterations=plateau_iterations,
                duration_seconds=duration_seconds,
                elapsed_seconds=elapsed_seconds,
                llm_calls=llm_calls,
                llm_call_budget=llm_call_budget,
                queries_executed=queries_executed,
                max_queries=max_queries,
            )
        except Exception as exc:  # noqa: BLE001 — telemetry must never kill research
            logger.warning(
                f"Session {self.session_id}: trajectory recording skipped for "
                f"iteration {iteration} ({type(exc).__name__}: {exc})."
            )
            return None

    async def _record(self, **kwargs: Any) -> RecordedStep:
        iteration: int = kwargs["iteration"]
        state_before = self._state_before

        urls: list[str] = kwargs["source_urls"]
        domains = {compute_url_domain(url) for url in urls if url}
        new_domains = len(domains - self._seen_domains)
        self._seen_domains |= domains

        # A contradiction leaves the unresolved set either because it was explicitly
        # resolved or because the versioning layer recognised it as one fact observed
        # twice. Both are real resolutions, so the drop in the count counts too.
        resolved_delta = max(
            0,
            kwargs["resolved_contradictions"] - state_before.resolved_contradictions,
            state_before.unresolved_contradictions
            - kwargs["unresolved_contradictions"],
        )

        credibility = kwargs["source_credibilities"]
        source_quality = (
            round(sum(credibility) / len(credibility), 4) if credibility else 0.0
        )
        confidence_distribution = {"high": 0, "medium": 0, "low": 0}
        for label in kwargs["claim_confidences"]:
            key = (label or "medium").lower()
            confidence_distribution[key] = confidence_distribution.get(key, 0) + 1
        low_quality_sources = sum(
            1 for score in credibility if float(score or 0) < 0.4
        )

        state_after = build_research_state(
            session_id=self.session_id,
            question=self.question,
            iteration=iteration,
            depth=self.depth,
            max_iterations=self.max_iterations,
            total_sources=kwargs["total_sources"],
            total_claims=kwargs["total_claims"],
            total_nodes=kwargs["total_nodes"],
            total_edges=kwargs["total_edges"],
            information_gain=kwargs["information_gain"],
            coverage=kwargs["coverage"],
            unresolved_contradictions=kwargs["unresolved_contradictions"],
            resolved_contradictions=state_before.resolved_contradictions
            + resolved_delta,
            gaps=kwargs["gaps"],
            facet_coverage=kwargs["facet_coverage"],
            source_quality=source_quality,
            source_diversity=len(self._seen_domains),
            confidence_distribution=confidence_distribution,
            duplicate_count=kwargs["duplicate_claim_count"],
            time_elapsed=kwargs["elapsed_seconds"],
            remaining_time=max(
                0.0, self.max_research_time_minutes * 60 - kwargs["elapsed_seconds"]
            ),
            remaining_search_budget=max(
                0, kwargs["max_queries"] - kwargs["queries_executed"]
            ),
            remaining_llm_budget=max(
                0, kwargs["llm_call_budget"] - kwargs["llm_calls"]
            ),
            previous_action=kwargs["executed_action"],
            previous_reward=self._last_reward,
            current_query=kwargs["action_parameters"].get("query"),
            contradictions_are_new=kwargs["contradictions_are_new"],
            plateau_iterations=kwargs["plateau_iterations"],
            llm_calls=kwargs["llm_calls"],
        )

        components = compute_reward_components(
            information_gain=kwargs["information_gain"],
            avg_credibility=source_quality,
            coverage_before=state_before.coverage,
            coverage_after=state_after.coverage,
            unresolved_contradictions=kwargs["unresolved_contradictions"],
            resolved_contradictions=resolved_delta,
            new_domains=new_domains,
            duplicate_findings=kwargs["duplicate_claim_count"]
            - state_before.duplicate_count,
            new_sources=kwargs["new_sources"],
            low_quality_sources=low_quality_sources,
            repeated_action_without_yield=is_repeated_without_yield(
                action=kwargs["executed_action"],
                previous_action=self._last_action,
                information_gain=kwargs["information_gain"],
                new_sources=kwargs["new_sources"],
                new_claims=kwargs["new_claims"],
            ),
            duration_seconds=kwargs["duration_seconds"],
            llm_calls=kwargs["llm_calls"],
            llm_call_budget=kwargs["llm_call_budget"],
        )

        observation = StateObservation(
            query=kwargs["action_parameters"].get("query"),
            facet=kwargs["action_parameters"].get("facet"),
            sources_added=kwargs["new_sources"],
            claims_added=kwargs["new_claims"],
            nodes_added=kwargs["new_nodes"],
            edges_added=kwargs["new_edges"],
            new_domains=new_domains,
            contradictions_found=kwargs["unresolved_contradictions"],
            contradictions_resolved=resolved_delta,
            gaps_found=list(kwargs["gaps"])[:8],
            duplicate_claims=kwargs["duplicate_claim_count"],
            low_quality_sources=low_quality_sources,
            llm_calls=kwargs["llm_calls"],
        )

        done = is_stop(kwargs["next_action"])
        action_parameters = {
            key: value
            for key, value in kwargs["action_parameters"].items()
            if value is not None
        }
        action_parameters["action"] = kwargs["executed_action"]
        action_parameters["next_action"] = kwargs["next_action"]

        async with _session_factory() as db:
            transition = await TransitionRepository(db).upsert(
                session_id=self.session_id,
                iteration=iteration,
                state_before=state_before.to_dict(),
                state_after=state_after.to_dict(),
                action_type=kwargs["executed_action"],
                action_parameters=action_parameters,
                observation=observation.to_dict(),
                reward=components.total,
                reward_components=components.to_dict(),
                information_gain=kwargs["information_gain"],
                coverage_before=state_before.coverage,
                coverage_after=state_after.coverage,
                contradictions_before=state_before.unresolved_contradictions,
                contradictions_after=kwargs["unresolved_contradictions"],
                sources_added=kwargs["new_sources"],
                claims_added=kwargs["new_claims"],
                execution_time=kwargs["duration_seconds"],
                policy_source="JEV",
                done=done,
                state_hash=state_after.state_hash(),
                state_bytes=state_after.state_size(),
            )

            # The reward of the action executed this iteration belongs to the
            # prediction made for it one step earlier.
            if self._last_prediction_id:
                await PredictionRepository(db).update_reward(
                    self._last_prediction_id, components.total
                )
            await db.commit()

        step = RecordedStep(
            transition_id=transition.id,
            iteration=iteration,
            reward=components.total,
            components=components,
            observation={**observation.to_dict(), "action": kwargs["executed_action"]},
            state_hash=state_after.state_hash(),
            state_bytes=state_after.state_size(),
        )

        # ─── shadow: what would the learned policy have done next? ───────────
        if self.shadow_enabled:
            step.shadow = await self._shadow(
                state_after=state_after,
                jev_action=kwargs["next_action"],
                jev_reasoning=kwargs["next_action_reasoning"],
            )

        self._state_before = state_after
        self._last_action = kwargs["executed_action"]
        self._last_reward = components.total
        logger.info(
            f"Session {self.session_id} transition {iteration}: "
            f"{kwargs['executed_action']} reward {components.total:+.3f} "
            f"(state {state_after.state_size()}B)"
        )
        return step

    async def _shadow(
        self,
        *,
        state_after: ResearchState,
        jev_action: str,
        jev_reasoning: str,
    ) -> dict[str, Any] | None:
        """Record the policy's recommendation without acting on it."""
        await self._load_policy()
        if self._policy is None:
            return None

        try:
            prediction: PolicyPrediction = self._policy.predict(
                state_after, executable_actions()
            )
            jev_expected = JevPolicy().expected_value(state_after, jev_action)
            async with _session_factory() as db:
                row = await PredictionRepository(db).create(
                    session_id=self.session_id,
                    iteration=state_after.iteration,
                    policy_id=self._policy_id,
                    state_key=state_after.state_key(),
                    state=state_after.to_dict(),
                    jev_action=jev_action,
                    jev_reasoning=jev_reasoning,
                    jev_expected_value=jev_expected,
                    rl_action=prediction.action,
                    rl_expected_value=prediction.expected_value,
                    rl_scores=prediction.scores,
                    rl_support=prediction.support_total,
                    fallback=prediction.fallback,
                    estimated_rl_reward=prediction.expected_value,
                    disagreement=prediction.action.upper() != jev_action.upper(),
                )
                await db.commit()
            self._last_prediction_id = row.id
            return {
                "policy_id": self._policy_id,
                "policy_algorithm": self._policy.describe()["algorithm"],
                "jev_action": jev_action,
                "jev_expected_value": jev_expected,
                "rl_action": prediction.action,
                "rl_expected_value": prediction.expected_value,
                "rl_scores": prediction.scores,
                "support": prediction.support_total,
                "fallback": prediction.fallback,
                "disagreement": prediction.action.upper() != jev_action.upper(),
                "prediction_id": row.id,
            }
        except Exception as exc:  # noqa: BLE001 — the shadow is inert by contract
            # A broken policy, a failed write, an unexpected shape: none of it may cost
            # the run its transition or its research progress.
            logger.warning(
                f"Session {self.session_id}: shadow prediction skipped "
                f"({type(exc).__name__}: {exc})."
            )
            return None
