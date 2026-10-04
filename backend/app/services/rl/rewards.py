"""Named reward components (V2 2.4).

The V1 reward was a single opaque number::

    reward = information_gain * 2.0 + avg_credibility - contradictions * 0.4 - 0.05

It is kept, unchanged, as ``metrics.compute_reward_signal`` — existing decisions still
carry it and the offline evaluation compares against it. What V2 adds is a *named*
version of the same signal, so a transition can be explained ("reward +2.41: +1.80
information gain, +0.62 evidence quality, −0.05 action cost") rather than asserted.

Compatibility is deliberate and exactly holds: with no coverage movement, no new
domains, no duplicates, no low-quality sources and zero measured duration/calls, the
V2 total equals the V1 signal bit for bit. Every new term starts at zero and can only
push the reward away from the baseline when there is data to justify it.

Weights are module constants so the evaluation report can show the formula instead of
asking readers to trust it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.services.metrics import compute_reward_signal

# ─── positive weights ────────────────────────────────────────────────────────
# Kept identical to V1 so the baseline comparison stays honest.
INFORMATION_GAIN_WEIGHT = 2.0
EVIDENCE_QUALITY_WEIGHT = 1.0
# New evidence for a dimension that had none is the most valuable research outcome,
# so coverage movement is weighted above a marginal gain in claim count.
COVERAGE_GAIN_WEIGHT = 3.0
CONTRADICTION_RESOLUTION_WEIGHT = 0.5
# Diminishing: the third new publisher says less than the second.
SOURCE_DIVERSITY_WEIGHT = 0.1
SOURCE_DIVERSITY_CAP = 3

# ─── penalties ───────────────────────────────────────────────────────────────
REDUNDANCY_PENALTY_PER_DUPLICATE = 0.3
LOW_QUALITY_SOURCE_PENALTY = 0.25
LOW_QUALITY_CREDIBILITY_FLOOR = 0.4
# The V1 action cost, now the floor of a named penalty.
BASE_ACTION_PENALTY = 0.05
# Extra cost when an action was repeated with no yield at all — the loop paying for
# the same result twice.
UNNECESSARY_ACTION_PENALTY = 0.35
UNNECESSARY_GAIN_FLOOR = 0.05
TIME_COST_MAX_PENALTY = 0.3
TIME_COST_REFERENCE_SECONDS = 600.0
BUDGET_COST_MAX_PENALTY = 0.5
UNRESOLVED_CONTRADICTION_PENALTY = 0.4

POSITIVE_FIELDS = (
    "information_gain_reward",
    "evidence_quality_reward",
    "coverage_gain_reward",
    "contradiction_resolution_reward",
    "source_diversity_reward",
)

PENALTY_FIELDS = (
    "redundancy_penalty",
    "low_quality_source_penalty",
    "unnecessary_action_penalty",
    "time_cost_penalty",
    "budget_cost_penalty",
    "unresolved_contradiction_penalty",
)


@dataclass(frozen=True)
class RewardComponents:
    """One transition's reward, decomposed into named, independently inspectable parts."""

    information_gain_reward: float = 0.0
    evidence_quality_reward: float = 0.0
    coverage_gain_reward: float = 0.0
    contradiction_resolution_reward: float = 0.0
    source_diversity_reward: float = 0.0
    redundancy_penalty: float = 0.0
    low_quality_source_penalty: float = 0.0
    unnecessary_action_penalty: float = 0.0
    time_cost_penalty: float = 0.0
    budget_cost_penalty: float = 0.0
    #: V1's unresolved-contradiction term, kept as a named component rather than
    #: folded into another penalty so the baseline stays reproducible.
    unresolved_contradiction_penalty: float = 0.0
    #: The untouched V1 signal for the same iteration, for baseline comparison.
    v1_reward: float = 0.0

    @property
    def positive_total(self) -> float:
        return round(sum(getattr(self, name) for name in POSITIVE_FIELDS), 4)

    @property
    def penalty_total(self) -> float:
        return round(sum(getattr(self, name) for name in PENALTY_FIELDS), 4)

    @property
    def total(self) -> float:
        """total = sum(positive rewards) − sum(penalties)."""
        return round(self.positive_total - self.penalty_total, 4)

    def to_dict(self) -> dict[str, Any]:
        payload = {name: round(getattr(self, name), 4) for name in asdict(self)}
        payload["positive_total"] = self.positive_total
        payload["penalty_total"] = self.penalty_total
        payload["total"] = self.total
        return payload

    def explain(self) -> list[dict[str, Any]]:
        """Ordered, human-readable reasons a transition scored what it scored.

        The evaluation page renders this directly, which is the point: a reward that
        cannot be explained cannot be tuned.
        """
        reasons: list[str] = []
        rows: list[dict[str, Any]] = []

        def add(field_name: str, reason: str) -> None:
            value = round(getattr(self, field_name), 4)
            if value == 0:
                return
            rows.append(
                {
                    "component": field_name,
                    "value": value,
                    "reason": reason,
                    "direction": "credit" if field_name in POSITIVE_FIELDS else "debit",
                }
            )
            reasons.append(f"{reason} ({value:+.2f})")

        add("information_gain_reward", "New claims and entities added this iteration")
        add("evidence_quality_reward", "Mean credibility of the evidence held")
        add("coverage_gain_reward", "Coverage of the question improved")
        add(
            "contradiction_resolution_reward",
            "Conflicting claims were resolved",
        )
        add("source_diversity_reward", "New independent publishers entered the evidence")
        add("redundancy_penalty", "Duplicate findings were paid for again")
        add("low_quality_source_penalty", "Low-credibility sources were added")
        add("unnecessary_action_penalty", "Action cost, or a repeat with no new evidence")
        add("time_cost_penalty", "Wall-clock time spent")
        add("budget_cost_penalty", "Share of the model-call budget spent")
        add(
            "unresolved_contradiction_penalty",
            "Contradictions are still unresolved",
        )
        return rows


def compute_reward_components(
    *,
    information_gain: float,
    avg_credibility: float,
    coverage_before: float = 0.0,
    coverage_after: float = 0.0,
    unresolved_contradictions: int = 0,
    resolved_contradictions: int = 0,
    new_domains: int = 0,
    duplicate_findings: int = 0,
    new_sources: int = 0,
    low_quality_sources: int = 0,
    repeated_action_without_yield: bool = False,
    duration_seconds: float = 0.0,
    llm_calls: int = 0,
    llm_call_budget: int = 0,
) -> RewardComponents:
    """Compute every reward component for one transition.

    All arguments are observables of the iteration that just ran; nothing here makes
    a model call or reads the database.
    """
    coverage_delta = max(0.0, coverage_after - coverage_before)
    diversity_credit = min(max(0, new_domains), SOURCE_DIVERSITY_CAP)

    time_penalty = min(
        TIME_COST_MAX_PENALTY,
        max(0.0, duration_seconds) / TIME_COST_REFERENCE_SECONDS * TIME_COST_MAX_PENALTY,
    )
    budget_penalty = 0.0
    if llm_call_budget > 0:
        budget_penalty = min(
            BUDGET_COST_MAX_PENALTY,
            (max(0, llm_calls) / llm_call_budget) * BUDGET_COST_MAX_PENALTY,
        )

    action_penalty = BASE_ACTION_PENALTY
    if repeated_action_without_yield:
        action_penalty += UNNECESSARY_ACTION_PENALTY

    return RewardComponents(
        information_gain_reward=round(
            information_gain * INFORMATION_GAIN_WEIGHT, 4
        ),
        evidence_quality_reward=round(avg_credibility * EVIDENCE_QUALITY_WEIGHT, 4),
        coverage_gain_reward=round(coverage_delta * COVERAGE_GAIN_WEIGHT, 4),
        contradiction_resolution_reward=round(
            resolved_contradictions * CONTRADICTION_RESOLUTION_WEIGHT, 4
        ),
        source_diversity_reward=round(
            diversity_credit * SOURCE_DIVERSITY_WEIGHT, 4
        ),
        redundancy_penalty=round(
            duplicate_findings * REDUNDANCY_PENALTY_PER_DUPLICATE, 4
        ),
        low_quality_source_penalty=round(
            low_quality_sources * LOW_QUALITY_SOURCE_PENALTY, 4
        ),
        unnecessary_action_penalty=round(action_penalty, 4),
        time_cost_penalty=round(time_penalty, 4),
        budget_cost_penalty=round(budget_penalty, 4),
        unresolved_contradiction_penalty=round(
            unresolved_contradictions * UNRESOLVED_CONTRADICTION_PENALTY, 4
        ),
        # The V1 formula over the same inputs, so old and new numbers are comparable.
        v1_reward=compute_reward_signal(
            information_gain=information_gain,
            avg_credibility=avg_credibility,
            unresolved_contradictions=unresolved_contradictions,
        ),
    )


def components_from_dict(payload: dict[str, Any] | None) -> RewardComponents:
    """Rebuild components from stored JSON, ignoring unknown or derived keys."""
    if not payload:
        return RewardComponents()
    known = {
        name: float(payload[name])
        for name in (
            *POSITIVE_FIELDS,
            *PENALTY_FIELDS,
            "v1_reward",
        )
        if isinstance(payload.get(name), (int, float))
    }
    return RewardComponents(**known)


def explain_components(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Human-readable reasons for a stored reward, for the inspection API."""
    return components_from_dict(payload).explain()


def reward_formula() -> dict[str, Any]:
    """The exact formula, exposed so the API and UI can document themselves."""
    return {
        "version": "v2",
        "positive": {
            "information_gain_reward": f"information_gain * {INFORMATION_GAIN_WEIGHT}",
            "evidence_quality_reward": f"avg_credibility * {EVIDENCE_QUALITY_WEIGHT}",
            "coverage_gain_reward": f"max(0, coverage_after - coverage_before) * {COVERAGE_GAIN_WEIGHT}",
            "contradiction_resolution_reward": (
                f"resolved_contradictions * {CONTRADICTION_RESOLUTION_WEIGHT}"
            ),
            "source_diversity_reward": (
                f"min(new_domains, {SOURCE_DIVERSITY_CAP}) * {SOURCE_DIVERSITY_WEIGHT}"
            ),
        },
        "penalties": {
            "redundancy_penalty": (
                f"duplicate_findings * {REDUNDANCY_PENALTY_PER_DUPLICATE}"
            ),
            "low_quality_source_penalty": (
                f"low_quality_sources * {LOW_QUALITY_SOURCE_PENALTY}"
            ),
            "unnecessary_action_penalty": (
                f"{BASE_ACTION_PENALTY} base"
                f" + {UNNECESSARY_ACTION_PENALTY} when an action repeats without yield"
            ),
            "time_cost_penalty": (
                f"duration_seconds / {int(TIME_COST_REFERENCE_SECONDS)}"
                f" * {TIME_COST_MAX_PENALTY}, capped"
            ),
            "budget_cost_penalty": (
                f"llm_calls / llm_call_budget * {BUDGET_COST_MAX_PENALTY}, capped"
            ),
            "unresolved_contradiction_penalty": (
                f"unresolved_contradictions * {UNRESOLVED_CONTRADICTION_PENALTY}"
            ),
        },
        "total": "sum(positive) - sum(penalties)",
        "v1_equivalent": (
            "compute_reward_signal(information_gain, avg_credibility, "
            "unresolved_contradictions)"
        ),
    }


def is_repeated_without_yield(
    *, action: str, previous_action: str | None, information_gain: float,
    new_sources: int, new_claims: int
) -> bool:
    """Whether this iteration repeated the previous action and learned nothing.

    A legitimate VERIFY can repeat across iterations while it closes a contradiction,
    so the flag requires *both* a repeat and zero measured yield.
    """
    if not previous_action or str(action).upper() != str(previous_action).upper():
        return False
    return (
        information_gain < UNNECESSARY_GAIN_FLOOR
        and new_sources <= 0
        and new_claims <= 0
    )
