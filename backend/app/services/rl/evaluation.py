"""JEV vs RL offline evaluation (V2 2.8 / 2.9).

The evaluation replays recorded transitions and asks each policy what it would do at
the *same* historical state. That symmetry is the whole point — and so is being
honest about what cannot be observed:

* The dataset was produced by JEV. When a policy picks the action that was actually
  executed, the outcome is **ground truth** and counts as an observed step.
* When it picks something else, no one ran that action, so its reward is the policy's
  own estimate. Those steps are marked ``counterfactual`` and are reported separately
  instead of being silently averaged into the same number.

Consequently every metric carries ``observed_steps`` / ``counterfactual_steps``, and
the report says which basis each figure rests on. A comparison that hid that
distinction would be decoration, not evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.rl.actions import action_spec, executable_actions
from app.services.rl.dataset import TrajectoryDataset, TransitionRecord
from app.services.rl.policy import ActionPolicy

#: Seconds charged for a counterfactual step when its real duration is unknown: the
#: mean duration of the steps that were actually executed in the same dataset.
DEFAULT_COUNTERFACTUAL_SECONDS = 30.0

#: Below this information gain an executed iteration counts as yielding nothing.
UNNECESSARY_GAIN_FLOOR = 0.05


@dataclass
class StepEvaluation:
    """One (state, action) decision made by a policy during replay."""

    session_id: str
    iteration: int
    state_key: str
    action: str
    recorded_action: str
    executed: bool
    reward: float | None
    estimated: bool
    information_gain: float
    coverage_before: float
    coverage_after: float
    contradictions_before: int
    contradictions_after: int
    duplicate_query: bool
    unnecessary_action: bool
    execution_time: float
    done: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "iteration": self.iteration,
            "state_key": self.state_key,
            "action": self.action,
            "recorded_action": self.recorded_action,
            "executed": self.executed,
            "reward": None if self.reward is None else round(self.reward, 4),
            "estimated": self.estimated,
            "information_gain": round(self.information_gain, 4),
            "coverage_before": round(self.coverage_before, 4),
            "coverage_after": round(self.coverage_after, 4),
            "duplicate_query": self.duplicate_query,
            "unnecessary_action": self.unnecessary_action,
            "done": self.done,
        }


@dataclass
class PolicyMetrics:
    """Aggregate outcome of one policy over the dataset."""

    policy: str
    steps: int = 0
    observed_steps: int = 0
    counterfactual_steps: int = 0
    unestimable_steps: int = 0
    total_reward: float = 0.0
    average_reward: float = 0.0
    average_information_gain: float = 0.0
    coverage_improvement: float = 0.0
    average_iterations: float = 0.0
    duplicate_search_rate: float = 0.0
    contradiction_resolution_rate: float = 0.0
    stop_rate: float = 0.0
    unnecessary_action_rate: float = 0.0
    research_cost_seconds: float = 0.0
    time_to_convergence: float | None = None
    action_distribution: dict[str, int] = field(default_factory=dict)
    estimated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "steps": self.steps,
            "observed_steps": self.observed_steps,
            "counterfactual_steps": self.counterfactual_steps,
            "unestimable_steps": self.unestimable_steps,
            "total_reward": round(self.total_reward, 4),
            "average_reward": round(self.average_reward, 4),
            "average_information_gain": round(self.average_information_gain, 4),
            "coverage_improvement": round(self.coverage_improvement, 4),
            "average_iterations": round(self.average_iterations, 4),
            "duplicate_search_rate": round(self.duplicate_search_rate, 4),
            "contradiction_resolution_rate": round(
                self.contradiction_resolution_rate, 4
            ),
            "stop_rate": round(self.stop_rate, 4),
            "unnecessary_action_rate": round(self.unnecessary_action_rate, 4),
            "research_cost_seconds": round(self.research_cost_seconds, 2),
            "time_to_convergence": (
                None
                if self.time_to_convergence is None
                else round(self.time_to_convergence, 4)
            ),
            "action_distribution": dict(self.action_distribution),
            "estimated": self.estimated,
        }


@dataclass
class EvaluationReport:
    """One evaluation run: metrics, breakdowns and the basis for every number."""

    policy: str
    baseline: str | None
    dataset_version: str
    dataset_hash: str
    dataset_size: int
    sessions: list[str]
    max_steps: int | None
    metrics: PolicyMetrics
    baseline_metrics: PolicyMetrics | None = None
    comparison: dict[str, Any] = field(default_factory=dict)
    per_session: list[dict[str, Any]] = field(default_factory=list)
    per_action: list[dict[str, Any]] = field(default_factory=list)
    steps: list[StepEvaluation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "baseline": self.baseline,
            "dataset_version": self.dataset_version,
            "dataset_hash": self.dataset_hash,
            "dataset_size": self.dataset_size,
            "sessions": self.sessions,
            "max_steps": self.max_steps,
            "metrics": self.metrics.to_dict(),
            "baseline_metrics": (
                self.baseline_metrics.to_dict() if self.baseline_metrics else None
            ),
            "comparison": self.comparison,
            "per_session": self.per_session,
            "per_action": self.per_action,
            "notes": self.notes,
        }


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def evaluate(
    dataset: TrajectoryDataset,
    policy: ActionPolicy,
    *,
    baseline: ActionPolicy | None = None,
    max_steps: int | None = None,
) -> EvaluationReport:
    """Replay every recorded state through ``policy`` (and optionally a baseline).

    The same transitions, the same state objects and the same step cap are used for
    both policies, so any difference in the numbers comes from the decisions.
    """
    steps = _replay(dataset, policy, max_steps)
    metrics = _aggregate(steps, policy.name, dataset, estimate=policy.name != "jev")

    baseline_metrics: PolicyMetrics | None = None
    baseline_steps: list[StepEvaluation] = []
    if baseline is not None:
        baseline_steps = _replay(dataset, baseline, max_steps)
        baseline_metrics = _aggregate(
            baseline_steps, baseline.name, dataset, estimate=baseline.name != "jev"
        )

    report = EvaluationReport(
        policy=policy.name,
        baseline=baseline.name if baseline else None,
        dataset_version=dataset.version,
        dataset_hash=dataset.dataset_hash(),
        dataset_size=len(dataset.records),
        sessions=dataset.sessions,
        max_steps=max_steps,
        metrics=metrics,
        baseline_metrics=baseline_metrics,
        comparison=_compare(metrics, baseline_metrics),
        per_session=_per_session(steps, baseline_steps if baseline else None),
        per_action=_per_action(steps, baseline_steps if baseline else None),
        steps=steps,
        notes=_notes(metrics),
    )
    return report


def _replay(
    dataset: TrajectoryDataset,
    policy: ActionPolicy,
    max_steps: int | None,
) -> list[StepEvaluation]:
    """Walk each session in iteration order and ask the policy for an action."""
    steps: list[StepEvaluation] = []
    by_session: dict[str, list[TransitionRecord]] = {}
    for record in dataset.records:
        by_session.setdefault(record.session_id, []).append(record)

    for session_id in sorted(by_session):
        records = sorted(by_session[session_id], key=lambda item: item.iteration)
        seen_queries: set[str] = set()
        previous_action: str | None = None
        for record in records:
            if max_steps is not None and len(
                [s for s in steps if s.session_id == session_id]
            ) >= max_steps:
                break

            state = record.state()
            if state is None:
                continue

            prediction = policy.predict(state, executable_actions())
            action = prediction.action.upper()
            recorded = record.action.upper()
            executed = action == recorded

            query = str(record.action_parameters.get("query") or "")
            duplicate = bool(query) and query in seen_queries
            if query:
                seen_queries.add(query)

            unnecessary = False
            if executed:
                unnecessary = (
                    previous_action == action
                    and record.information_gain < UNNECESSARY_GAIN_FLOOR
                    and record.sources_added <= 0
                    and record.claims_added <= 0
                )

            reward: float | None
            estimated = False
            if executed:
                reward = float(record.reward)
            else:
                reward = prediction.scores.get(action)
                if reward is None:
                    reward = policy.expected_value(state, action)
                estimated = reward is not None

            steps.append(
                StepEvaluation(
                    session_id=session_id,
                    iteration=record.iteration,
                    state_key=state.state_key(),
                    action=action,
                    recorded_action=recorded,
                    executed=executed,
                    reward=reward,
                    estimated=estimated,
                    information_gain=record.information_gain,
                    coverage_before=record.coverage_before,
                    coverage_after=record.coverage_after,
                    contradictions_before=record.contradictions_before,
                    contradictions_after=record.contradictions_after,
                    duplicate_query=duplicate,
                    unnecessary_action=unnecessary,
                    execution_time=record.execution_time,
                    done=record.done,
                )
            )
            previous_action = action

    return steps


def _aggregate(
    steps: list[StepEvaluation],
    policy_name: str,
    dataset: TrajectoryDataset,
    *,
    estimate: bool,
) -> PolicyMetrics:
    """Roll a replay up into the metrics the dashboard reports."""
    rewarded = [step for step in steps if step.reward is not None]
    executed = [step for step in steps if step.executed]
    counterfactual = [step for step in steps if not step.executed]
    unestimable = [step for step in counterfactual if step.reward is None]

    rewards = [float(step.reward) for step in rewarded]
    gains = [step.information_gain for step in executed]
    coverage_gain = sum(
        max(0.0, step.coverage_after - step.coverage_before) for step in executed
    )
    resolved = sum(
        max(0, step.contradictions_before - step.contradictions_after)
        for step in executed
    )
    contradictions_before = sum(step.contradictions_before for step in executed)

    search_steps = [
        step for step in executed if step.action in ("SEARCH", "EXPAND_QUERY")
    ]
    duplicates = sum(1 for step in search_steps if step.duplicate_query)

    sessions = sorted({step.session_id for step in steps})
    first_stop: dict[str, int] = {}
    for step in steps:
        if step.action == "STOP" and step.session_id not in first_stop:
            first_stop[step.session_id] = step.iteration
    sessions_with_stop = len(first_stop)

    mean_observed_seconds = _mean(
        [step.execution_time for step in executed if step.execution_time > 0]
    ) or DEFAULT_COUNTERFACTUAL_SECONDS
    cost = sum(step.execution_time for step in executed) + sum(
        action_spec(step.action).cost_weight * mean_observed_seconds
        for step in counterfactual
    )

    action_distribution: dict[str, int] = {}
    for step in steps:
        action_distribution[step.action] = action_distribution.get(step.action, 0) + 1

    return PolicyMetrics(
        policy=policy_name,
        steps=len(steps),
        observed_steps=len(executed),
        counterfactual_steps=len(counterfactual),
        unestimable_steps=len(unestimable),
        total_reward=round(sum(rewards), 4),
        average_reward=_mean(rewards),
        average_information_gain=_mean(gains),
        coverage_improvement=round(coverage_gain, 4),
        average_iterations=(
            round(len(steps) / len(sessions), 4) if sessions else 0.0
        ),
        duplicate_search_rate=_rate(duplicates, len(search_steps)),
        contradiction_resolution_rate=_rate(resolved, contradictions_before),
        stop_rate=_rate(sessions_with_stop, len(sessions)),
        unnecessary_action_rate=_rate(
            sum(1 for step in executed if step.unnecessary_action), len(executed)
        ),
        research_cost_seconds=cost,
        time_to_convergence=(
            _mean([float(value) for value in first_stop.values()])
            if first_stop
            else None
        ),
        action_distribution=action_distribution,
        estimated=estimate,
    )


def _compare(
    metrics: PolicyMetrics, baseline: PolicyMetrics | None
) -> dict[str, Any]:
    """Policy-versus-baseline deltas plus the agreement it was measured on."""
    if baseline is None:
        return {}

    total = metrics.steps or 0
    agreed = metrics.observed_steps
    return {
        "agreement_rate": _rate(agreed, total),
        "disagreement_rate": _rate(metrics.counterfactual_steps, total),
        "agreement_steps": agreed,
        "disagreement_steps": metrics.counterfactual_steps,
        "reward_delta": round(metrics.average_reward - baseline.average_reward, 4),
        "total_reward_delta": round(
            metrics.total_reward - baseline.total_reward, 4
        ),
        "information_gain_delta": round(
            metrics.average_information_gain - baseline.average_information_gain, 4
        ),
        "coverage_delta": round(
            metrics.coverage_improvement - baseline.coverage_improvement, 4
        ),
        "cost_delta_seconds": round(
            metrics.research_cost_seconds - baseline.research_cost_seconds, 2
        ),
        "time_to_convergence_delta": (
            None
            if metrics.time_to_convergence is None
            or baseline.time_to_convergence is None
            else round(
                metrics.time_to_convergence - baseline.time_to_convergence, 4
            )
        ),
        "baseline_estimated": baseline.estimated,
    }


def _per_session(
    steps: list[StepEvaluation],
    baseline_steps: list[StepEvaluation] | None,
) -> list[dict[str, Any]]:
    """Per-session breakdown, because an aggregate can hide a policy losing badly."""
    baseline_by_session: dict[str, list[StepEvaluation]] = {}
    for step in baseline_steps or []:
        baseline_by_session.setdefault(step.session_id, []).append(step)

    sessions: dict[str, list[StepEvaluation]] = {}
    for step in steps:
        sessions.setdefault(step.session_id, []).append(step)

    rows: list[dict[str, Any]] = []
    for session_id in sorted(sessions):
        group = sessions[session_id]
        rewards = [float(s.reward) for s in group if s.reward is not None]
        baseline_group = baseline_by_session.get(session_id)
        baseline_rewards = [
            float(s.reward) for s in baseline_group or [] if s.reward is not None
        ]
        rows.append(
            {
                "session_id": session_id,
                "steps": len(group),
                "observed_steps": sum(1 for s in group if s.executed),
                "counterfactual_steps": sum(1 for s in group if not s.executed),
                "average_reward": _mean(rewards),
                "total_reward": round(sum(rewards), 4),
                "baseline_average_reward": (
                    _mean(baseline_rewards) if baseline_group is not None else None
                ),
                "reward_delta": (
                    round(_mean(rewards) - _mean(baseline_rewards), 4)
                    if baseline_group is not None and baseline_rewards
                    else None
                ),
                "final_coverage": round(group[-1].coverage_after, 4),
                "stopped": any(step.action == "STOP" for step in group),
            }
        )
    return rows


def _per_action(
    steps: list[StepEvaluation],
    baseline_steps: list[StepEvaluation] | None,
) -> list[dict[str, Any]]:
    """Per-action breakdown with sample sizes — the spec's ``ACTION = VERIFY`` view."""

    def group(rows: list[StepEvaluation]) -> dict[str, list[StepEvaluation]]:
        grouped: dict[str, list[StepEvaluation]] = {}
        for step in rows:
            grouped.setdefault(step.action, []).append(step)
        return grouped

    policy_groups = group(steps)
    baseline_groups = group(baseline_steps or [])

    rows: list[dict[str, Any]] = []
    for action in sorted(set(policy_groups) | set(baseline_groups)):
        policy_steps = policy_groups.get(action, [])
        baseline_group = baseline_groups.get(action, [])
        policy_rewards = [
            float(s.reward) for s in policy_steps if s.reward is not None
        ]
        baseline_rewards = [
            float(s.reward) for s in baseline_group if s.reward is not None
        ]
        rows.append(
            {
                "action": action,
                "sample_size": len(policy_steps),
                "observed_steps": sum(1 for s in policy_steps if s.executed),
                "counterfactual_steps": sum(1 for s in policy_steps if not s.executed),
                "average_reward": _mean(policy_rewards),
                "estimated": any(s.estimated for s in policy_steps),
                "baseline_sample_size": len(baseline_group),
                "baseline_average_reward": (
                    _mean(baseline_rewards) if baseline_group else None
                ),
                "reward_delta": (
                    round(_mean(policy_rewards) - _mean(baseline_rewards), 4)
                    if policy_rewards and baseline_rewards
                    else None
                ),
            }
        )
    return rows


def _notes(metrics: PolicyMetrics) -> list[str]:
    """The honest caveats, attached to every report so the UI cannot omit them."""
    notes: list[str] = []
    if metrics.counterfactual_steps:
        notes.append(
            f"{metrics.counterfactual_steps} of {metrics.steps} decisions differ from "
            "the recorded run; their rewards are policy estimates, not observed "
            "outcomes."
        )
    if metrics.unestimable_steps:
        notes.append(
            f"{metrics.unestimable_steps} counterfactual decision(s) fall outside the "
            "policy's learned contexts, so no reward estimate exists for them."
        )
    if metrics.estimated:
        notes.append(
            "This policy's totals mix observed and estimated rewards; the observed "
            "share is reported as observed_steps."
        )
    if not notes:
        notes.append(
            "Every decision matches the recorded trajectory, so all metrics are "
            "observed outcomes."
        )
    return notes
