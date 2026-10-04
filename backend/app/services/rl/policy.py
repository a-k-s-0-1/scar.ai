"""Offline research policy (V2 2.6) — lightweight, dependency-free, swappable.

The implemented algorithm is **contextual Monte-Carlo action-value estimation over
discretised state features**. Stated exactly:

1. A state is mapped to a bounded categorical context key by
   ``ResearchState.state_key()`` (coverage bin, gain bin, contradiction count, gaps,
   facet coverage, budget pressure, iteration phase, previous action).
2. From the recorded trajectories, for every context ``s`` and action ``a`` we keep a
   count ``n(s,a)`` and a reward sum ``G(s,a)``, so the raw estimate is the sample mean
   ``mean(s,a) = G(s,a) / n(s,a)``.
3. Estimates are shrunk toward the policy's global per-action mean with a Bayesian
   pseudo-count ``k``::

       Q(s, a) = (n(s,a) * mean(s,a) + k * global_mean(a)) / (n(s,a) + k)

   ``k`` is why a context observed once does not outrank a context observed fifty
   times: the first observation moves the estimate, but not all the way.
4. The policy recommends ``argmax_a Q(s,a)`` over the actions the orchestrator can
   execute, breaking ties in JEV's own preference order (VERIFY, EXPAND_QUERY, SEARCH,
   STOP) so a policy that has learned nothing behaves exactly like the baseline
   instead of randomly.
5. Below ``min_samples`` recorded transitions the table is not trusted at all and the
   policy defers to JEV, reporting ``fallback=True``.

This is explicitly **not** deep RL: there is no neural network, no gradient step, no
torch, and nothing is trained online. The whole model is a JSON object, which is why it
can be stored in a database row, diffed, and reviewed by hand.

A future PyTorch/Stable-Baselines3 implementation replaces this module behind the same
``predict``/``expected_value`` interface; nothing else in the application imports the
algorithm, only the interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.services.decision_engine import ActionType, DecisionEngine, KnowledgeState
from app.services.metrics import compute_reward_signal
from app.services.rl.actions import (
    ACTION_PRIORITY,
    executable_actions,
    is_executable,
)
from app.services.rl.dataset import DATASET_VERSION, TransitionRecord
from app.services.rl.research_state import ResearchState

#: Algorithm identity. Stored with every policy payload so a future implementation can
#: coexist with this one instead of overwriting it.
ALGORITHM = "contextual_monte_carlo"
POLICY_VERSION = "1.0"

#: Bayesian pseudo-count: how much evidence the global per-action mean is worth.
DEFAULT_SHRINKAGE = 2.0

#: Below this many recorded transitions the policy is not consulted at all.
DEFAULT_MIN_SAMPLES = 10

#: The dataset mean is the prior for an action never seen at all.
DEFAULT_PRIOR_REWARD = 0.0


@dataclass(frozen=True)
class PolicyPrediction:
    """One recommendation, with everything needed to explain or audit it."""

    action: str
    policy: str
    expected_value: float | None = None
    scores: dict[str, float] = field(default_factory=dict)
    support: dict[str, int] = field(default_factory=dict)
    support_total: int = 0
    fallback: bool = False
    state_key: str = ""
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "policy": self.policy,
            "expected_value": (
                None if self.expected_value is None else round(self.expected_value, 4)
            ),
            "scores": {k: round(v, 4) for k, v in self.scores.items()},
            "support": dict(self.support),
            "support_total": self.support_total,
            "fallback": self.fallback,
            "state_key": self.state_key,
            "explanation": self.explanation,
        }


class ActionPolicy(Protocol):
    """The seam a future trained policy implements.

    Only these five methods are used by the rest of the application: the shadow
    predictor, the evaluation engine and the API. Swapping the implementation does not
    touch the research loop.
    """

    name: str

    def predict(
        self,
        state: ResearchState,
        available_actions: list[str] | None = None,
    ) -> PolicyPrediction: ...

    def expected_value(self, state: ResearchState, action: str) -> float | None: ...

    def to_dict(self) -> dict[str, Any]: ...


def research_state_to_knowledge_state(state: ResearchState) -> KnowledgeState:
    """Adapt a stored ``ResearchState`` onto JEV's ``KnowledgeState`` input.

    Used by the shadow comparison and the JEV baseline policy, so both policies read
    the same observation instead of two subtly different ones.
    """
    return KnowledgeState(
        iteration=state.iteration,
        sources_count=state.total_sources,
        claims_count=state.total_claims,
        nodes_count=state.total_nodes,
        edges_count=state.total_edges,
        unresolved_contradictions=state.unresolved_contradictions,
        coverage_estimate=state.coverage,
        information_gain=state.information_gain,
        gaps=list(state.unresolved_gaps),
        max_iterations=state.max_iterations,
        elapsed_time_minutes=state.time_elapsed / 60.0,
        max_research_time_minutes=int(
            (state.time_elapsed + state.remaining_time) / 60.0
        ),
        previous_information_gain=state.information_gain,
        previous_coverage=state.coverage,
        plateau_iterations=state.plateau_iterations,
        contradictions_are_new=state.contradictions_are_new,
        facet_coverage=state.facet_coverage,
        facet_gaps=list(state.unresolved_gaps),
    )


class JevPolicy:
    """The baseline wrapped as a policy, so JEV and RL are compared through one seam."""

    name = "jev"

    def __init__(self) -> None:
        self.engine = DecisionEngine("baseline")

    def predict(
        self,
        state: ResearchState,
        available_actions: list[str] | None = None,
    ) -> PolicyPrediction:
        action, reasoning = self.engine.select_action(
            research_state_to_knowledge_state(state)
        )
        value = self.expected_value(state, action.value)
        return PolicyPrediction(
            action=action.value,
            policy=self.name,
            expected_value=value,
            scores={action.value: value} if value is not None else {},
            state_key=state.state_key(),
            explanation=reasoning,
        )

    def expected_value(self, state: ResearchState, action: str) -> float | None:
        """JEV's expected value proxy: the V1 reward signal evaluated on the state.

        JEV has no learned value function, so this is the same formula its decision log
        already recorded. It is reported as ``jev_expected_value`` and never presented
        as a measured reward.
        """
        if action.upper() != self.engine.select_action(
            research_state_to_knowledge_state(state)
        )[0].value.upper():
            return None
        return compute_reward_signal(
            information_gain=state.information_gain,
            avg_credibility=state.source_quality,
            unresolved_contradictions=state.unresolved_contradictions,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "algorithm": "hardcoded_heuristic",
            "notes": "V1 JEV policy; the production decision maker throughout V2.",
        }


class TabularPolicy:
    """Contextual Monte-Carlo action values over discretised states (see module doc)."""

    name = "rl"

    def __init__(
        self,
        *,
        action_counts: dict[str, dict[str, int]] | None = None,
        action_value_sums: dict[str, dict[str, float]] | None = None,
        global_counts: dict[str, int] | None = None,
        global_value_sums: dict[str, float] | None = None,
        shrinkage: float = DEFAULT_SHRINKAGE,
        min_samples: int = DEFAULT_MIN_SAMPLES,
        samples: int = 0,
        sessions: list[str] | None = None,
        dataset_version: str = DATASET_VERSION,
        dataset_hash: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.action_counts = action_counts or {}
        self.action_value_sums = action_value_sums or {}
        self.global_counts = global_counts or {}
        self.global_value_sums = global_value_sums or {}
        self.shrinkage = max(0.0, shrinkage)
        self.min_samples = max(0, min_samples)
        self.samples = samples
        self.sessions = sessions or []
        self.dataset_version = dataset_version
        self.dataset_hash = dataset_hash
        self.metadata = metadata or {}

    # ─── training ────────────────────────────────────────────────────────────
    @classmethod
    def train(
        cls,
        records: list[TransitionRecord],
        *,
        shrinkage: float = DEFAULT_SHRINKAGE,
        min_samples: int = DEFAULT_MIN_SAMPLES,
        dataset_version: str = DATASET_VERSION,
        dataset_hash: str = "",
    ) -> TabularPolicy:
        """Estimate action values from recorded transitions.

        Every transition contributes its own reward to its own context/action cell —
        Monte-Carlo returns, not bootstrapped values. The table is small by
        construction (bounded feature bins), so this is linear in the dataset.
        """
        action_counts: dict[str, dict[str, int]] = {}
        action_value_sums: dict[str, dict[str, float]] = {}
        global_counts: dict[str, int] = {}
        global_value_sums: dict[str, float] = {}

        for record in records:
            state = record.state()
            if state is None or not record.action:
                continue
            key = state.state_key()
            action = record.action.upper()
            reward = float(record.reward)

            cell_counts = action_counts.setdefault(key, {})
            cell_sums = action_value_sums.setdefault(key, {})
            cell_counts[action] = cell_counts.get(action, 0) + 1
            cell_sums[action] = cell_sums.get(action, 0.0) + reward
            global_counts[action] = global_counts.get(action, 0) + 1
            global_value_sums[action] = global_value_sums.get(action, 0.0) + reward

        return cls(
            action_counts=action_counts,
            action_value_sums=action_value_sums,
            global_counts=global_counts,
            global_value_sums=global_value_sums,
            shrinkage=shrinkage,
            min_samples=min_samples,
            samples=len(records),
            sessions=sorted({record.session_id for record in records}),
            dataset_version=dataset_version,
            dataset_hash=dataset_hash,
        )

    # ─── inference ───────────────────────────────────────────────────────────
    def global_mean(self, action: str) -> float:
        count = self.global_counts.get(action, 0)
        if count <= 0:
            return DEFAULT_PRIOR_REWARD
        return self.global_value_sums.get(action, 0.0) / count

    def expected_value(self, state: ResearchState, action: str) -> float | None:
        """Shrunk Q estimate for one (state, action), or ``None`` when unknown."""
        key = state.state_key()
        action = action.upper()
        count = self.action_counts.get(key, {}).get(action, 0)
        value_sum = self.action_value_sums.get(key, {}).get(action, 0.0)
        global_mean = self.global_mean(action)
        if count <= 0 and self.global_counts.get(action, 0) <= 0:
            return None
        local = value_sum / count if count > 0 else global_mean
        k = self.shrinkage
        return round((count * local + k * global_mean) / (count + k), 4)

    def _rank_score(self, action: str) -> float:
        return ACTION_PRIORITY.index(action) if action in ACTION_PRIORITY else 99

    def predict(
        self,
        state: ResearchState,
        available_actions: list[str] | None = None,
    ) -> PolicyPrediction:
        """Recommend an action for one state, with full supporting evidence."""
        candidates = [
            action
            for action in (available_actions or executable_actions())
            if is_executable(action)
        ]
        key = state.state_key()

        if self.samples < self.min_samples:
            baseline = JevPolicy().predict(state, candidates)
            return PolicyPrediction(
                action=baseline.action,
                policy=self.name,
                expected_value=None,
                support_total=self.samples,
                fallback=True,
                state_key=key,
                explanation=(
                    f"Only {self.samples} transition(s) in the dataset "
                    f"(minimum {self.min_samples}); deferring to JEV."
                ),
            )

        scores: dict[str, float] = {}
        support: dict[str, int] = {}
        for action in candidates:
            value = self.expected_value(state, action)
            support[action] = int(self.action_counts.get(key, {}).get(action, 0))
            if value is not None:
                scores[action] = value

        if not scores:
            baseline = JevPolicy().predict(state, candidates)
            return PolicyPrediction(
                action=baseline.action,
                policy=self.name,
                expected_value=None,
                support=support,
                support_total=sum(support.values()),
                fallback=True,
                state_key=key,
                explanation=(
                    "No action has been observed in this context; deferring to JEV."
                ),
            )

        # Highest value wins; ties fall back to JEV's preference order, which keeps the
        # recommendation deterministic and auditable. ``min`` over the negated value is
        # the same choice as sorting with a negated key, without building the list.
        best = min(scores, key=lambda a: (-scores[a], self._rank_score(a), a))
        best_support = support.get(best, 0)
        return PolicyPrediction(
            action=best,
            policy=self.name,
            expected_value=scores[best],
            scores=scores,
            support=support,
            support_total=sum(support.values()),
            state_key=key,
            explanation=(
                f"Highest estimated reward ({scores[best]:+.3f}) for context '{key}' "
                f"with {best_support} matching transition(s)."
            ),
        )

    # ─── persistence ─────────────────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "algorithm": ALGORITHM,
            "version": POLICY_VERSION,
            "dataset_version": self.dataset_version,
            "dataset_hash": self.dataset_hash,
            "shrinkage": self.shrinkage,
            "min_samples": self.min_samples,
            "samples": self.samples,
            "sessions": self.sessions,
            "feature_spec": {
                "source": "ResearchState.state_key()",
                "coverage_bins": ["very_low", "low", "medium", "high"],
                "gain_bins": ["flat", "some", "high"],
                "facets_bins": ["none", "partial", "good", "full"],
            },
            "action_priority": ACTION_PRIORITY,
            "action_counts": self.action_counts,
            "action_value_sums": self.action_value_sums,
            "global_counts": self.global_counts,
            "global_value_sums": self.global_value_sums,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> TabularPolicy | None:
        """Rebuild a policy from stored JSON, or ``None`` when it is not one of ours.

        Returning ``None`` (rather than raising) is the safety requirement: an
        unreadable policy must leave JEV in charge, not break a research session.
        """
        if not payload or payload.get("algorithm") != ALGORITHM:
            return None
        return cls(
            action_counts={
                str(key): {str(a): int(n) for a, n in (counts or {}).items()}
                for key, counts in (payload.get("action_counts") or {}).items()
            },
            action_value_sums={
                str(key): {str(a): float(v) for a, v in (sums or {}).items()}
                for key, sums in (payload.get("action_value_sums") or {}).items()
            },
            global_counts={
                str(a): int(n) for a, n in (payload.get("global_counts") or {}).items()
            },
            global_value_sums={
                str(a): float(v)
                for a, v in (payload.get("global_value_sums") or {}).items()
            },
            shrinkage=float(payload.get("shrinkage", DEFAULT_SHRINKAGE)),
            min_samples=int(payload.get("min_samples", DEFAULT_MIN_SAMPLES)),
            samples=int(payload.get("samples", 0)),
            sessions=list(payload.get("sessions") or []),
            dataset_version=str(payload.get("dataset_version", DATASET_VERSION)),
            dataset_hash=str(payload.get("dataset_hash", "")),
            metadata=dict(payload.get("metadata") or {}),
        )

    def describe(self) -> dict[str, Any]:
        """What this policy is, in the plainest terms, for the evaluation page."""
        distinct_contexts = len(self.action_counts)
        learned_cells = sum(
            1 for counts in self.action_counts.values() for n in counts.values() if n > 0
        )
        return {
            "policy": self.name,
            "algorithm": ALGORITHM,
            "version": POLICY_VERSION,
            "is_deep_rl": False,
            "trained_transitions": self.samples,
            "trained_sessions": len(self.sessions),
            "dataset_version": self.dataset_version,
            "dataset_hash": self.dataset_hash,
            "contexts": distinct_contexts,
            "learned_context_action_cells": learned_cells,
            "shrinkage_pseudo_count": self.shrinkage,
            "min_samples": self.min_samples,
            "available_actions": executable_actions(),
            "action_means": {
                action: round(self.global_mean(action), 4)
                for action in sorted(self.global_counts)
            },
            "notes": (
                "Tabular Monte-Carlo action values over discretised research states, "
                "shrunk toward the global per-action mean. No neural network, no "
                "gradients, no online updates; JEV remains the production policy."
            ),
        }


def jev_reference_action(state: ResearchState) -> str:
    """JEV's choice for one state — the baseline a policy must beat."""
    action = JevPolicy().predict(state).action
    return ActionType(action).value


def policy_expected_value(
    policy: ActionPolicy, state: ResearchState, action: str
) -> float | None:
    """Uniform access to a policy's value estimate, tolerating implementations
    that do not expose one (JEV's answer is a computed proxy, not a learned value)."""
    value = policy.expected_value(state, action)
    return None if value is None else round(float(value), 4)
