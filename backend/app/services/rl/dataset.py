"""Offline trajectory dataset (V2 2.5 / 2.6).

A trajectory is the tuple a policy learns from::

    state -> action -> observation -> reward -> next_state

V1 recorded *decisions* (state snapshot, chosen action, reasoning, a reward signal)
but never joined them to what happened next, so nothing in the database was a
learnable transition. ``research_transitions`` closes that loop; this module turns the
rows into a validated dataset without importing SQLAlchemy, so dataset building is
testable on plain dicts and the JSONL export is exactly what an external trainer would
receive.

Validation is part of the builder rather than a separate audit step: a dataset that
contains a broken transition trains a policy to expect a state it will never see, and
the failure is invisible at training time. Every issue is named and countable, and a
caller can either reject the dataset or inspect what was dropped.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from itertools import pairwise
from typing import Any

from app.services.rl.actions import ActionRequest, is_stop
from app.services.rl.research_state import ResearchState

#: Dataset schema version. Bump when the sample shape changes; stored on every
#: policy so a policy can never be applied to a dataset it was not trained for.
DATASET_VERSION = "v2.0"


@dataclass(frozen=True)
class TransitionRecord:
    """One persisted research step, detached from the ORM for learning."""

    id: str
    session_id: str
    iteration: int
    state_before: dict[str, Any] | None
    action: str
    action_parameters: dict[str, Any] = field(default_factory=dict)
    observation: dict[str, Any] = field(default_factory=dict)
    reward: float = 0.0
    reward_components: dict[str, Any] = field(default_factory=dict)
    information_gain: float = 0.0
    coverage_before: float = 0.0
    coverage_after: float = 0.0
    contradictions_before: int = 0
    contradictions_after: int = 0
    sources_added: int = 0
    claims_added: int = 0
    execution_time: float = 0.0
    state_after: dict[str, Any] | None = None
    policy_source: str = "JEV"
    done: bool = False
    created_at: datetime | None = None

    def state(self) -> ResearchState | None:
        """``state_before`` as a state object, or ``None`` when it is unusable."""
        return _safe_state(self.state_before)

    def next_state(self) -> ResearchState | None:
        return _safe_state(self.state_after)

    def action_request(self) -> ActionRequest | None:
        return ActionRequest.from_dict(
            {"action_type": self.action, "parameters": self.action_parameters}
        )

    def to_sample(self, include_metadata: bool = False) -> dict[str, Any]:
        """The learning sample: ``state, action, reward, next_state, done``."""
        sample: dict[str, Any] = {
            "state": self.state_before,
            "action": self.action,
            "reward": round(float(self.reward), 4),
            "next_state": self.state_after,
            "done": bool(self.done),
        }
        if include_metadata:
            sample["metadata"] = {
                "id": self.id,
                "session_id": self.session_id,
                "iteration": self.iteration,
                "policy_source": self.policy_source,
                "information_gain": round(float(self.information_gain), 4),
                "action_parameters": self.action_parameters,
                "observation": self.observation,
                "reward_components": self.reward_components,
                "coverage_before": round(float(self.coverage_before), 4),
                "coverage_after": round(float(self.coverage_after), 4),
                "sources_added": self.sources_added,
                "claims_added": self.claims_added,
                "execution_time": round(float(self.execution_time), 4),
                "created_at": self.created_at.isoformat() if self.created_at else None,
            }
        return sample

    def to_dict(self) -> dict[str, Any]:
        payload = self.to_sample(include_metadata=True)
        payload.update(payload.pop("metadata"))
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TransitionRecord:
        created = payload.get("created_at")
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created)
            except ValueError:
                created = None
        # An exported sample carries no top-level iteration or session id — they live
        # inside the state — so importing JSONL has to read them from there, otherwise
        # every imported transition looks like iteration 0 and is rejected as broken.
        state_before = payload.get("state") or payload.get("state_before") or {}
        state_after = payload.get("next_state") or payload.get("state_after") or {}
        session_id = str(
            payload.get("session_id")
            or (state_before.get("session_id") if isinstance(state_before, dict) else "")
            or (state_after.get("session_id") if isinstance(state_after, dict) else "")
            or ""
        )
        # A transition's own iteration is the iteration of its *resulting* state;
        # reading it from ``state_before`` would name every imported step one too low
        # and the first one 0, which the validator then rejects.
        iteration = int(
            payload.get("iteration")
            or (state_after.get("iteration") if isinstance(state_after, dict) else None)
            or (
                (state_before.get("iteration") or 0) + 1
                if isinstance(state_before, dict)
                else 0
            )
            or 0
        )
        return cls(
            id=str(payload.get("id", "")),
            session_id=session_id,
            iteration=iteration,
            state_before=payload.get("state") or payload.get("state_before"),
            action=str(payload.get("action") or ""),
            action_parameters=payload.get("action_parameters") or {},
            observation=payload.get("observation") or {},
            reward=float(payload.get("reward", 0.0) or 0.0),
            reward_components=payload.get("reward_components") or {},
            information_gain=float(payload.get("information_gain", 0.0) or 0.0),
            coverage_before=float(payload.get("coverage_before", 0.0) or 0.0),
            coverage_after=float(payload.get("coverage_after", 0.0) or 0.0),
            contradictions_before=int(payload.get("contradictions_before", 0) or 0),
            contradictions_after=int(payload.get("contradictions_after", 0) or 0),
            sources_added=int(payload.get("sources_added", 0) or 0),
            claims_added=int(payload.get("claims_added", 0) or 0),
            execution_time=float(payload.get("execution_time", 0.0) or 0.0),
            state_after=payload.get("next_state") or payload.get("state_after"),
            policy_source=str(payload.get("policy_source", "JEV")),
            done=bool(payload.get("done", False)),
            created_at=created if isinstance(created, datetime) else None,
        )


def _safe_state(payload: dict[str, Any] | None) -> ResearchState | None:
    """Parse a stored state, returning ``None`` rather than raising on bad data."""
    if not isinstance(payload, dict) or not payload:
        return None
    try:
        return ResearchState.from_dict(payload)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class DatasetIssue:
    """One reason a transition was rejected or flagged."""

    kind: str
    session_id: str
    iteration: int
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "session_id": self.session_id,
            "iteration": self.iteration,
            "detail": self.detail,
        }


@dataclass
class TrajectoryDataset:
    """Validated transitions, ready to train on or export."""

    version: str
    records: list[TransitionRecord]
    issues: list[DatasetIssue] = field(default_factory=list)
    dropped: int = 0
    dataset_hash_value: str = ""

    @property
    def sessions(self) -> list[str]:
        return sorted({record.session_id for record in self.records})

    @property
    def samples(self) -> list[dict[str, Any]]:
        return [record.to_sample() for record in self.records]

    def dataset_hash(self) -> str:
        """Content hash over the sample payloads, stable across processes."""
        if self.dataset_hash_value:
            return self.dataset_hash_value
        digest = hashlib.sha256()
        for sample in self.samples:
            digest.update(
                json.dumps(sample, sort_keys=True, separators=(",", ":")).encode("utf-8")
            )
        self.dataset_hash_value = digest.hexdigest()[:16]
        return self.dataset_hash_value

    def to_jsonl(self, include_metadata: bool = False) -> str:
        """One JSON object per line — the export format trainers actually consume."""
        return "\n".join(
            json.dumps(
                record.to_sample(include_metadata=include_metadata),
                sort_keys=True,
                separators=(",", ":"),
            )
            for record in self.records
        )

    def stats(self) -> dict[str, Any]:
        """Size, composition and outcome spread of the dataset."""
        rewards = [record.reward for record in self.records]
        gains = [record.information_gain for record in self.records]
        actions: dict[str, int] = {}
        sources = {"JEV": 0, "RL_SHADOW": 0, "OTHER": 0}
        for record in self.records:
            actions[record.action] = actions.get(record.action, 0) + 1
            sources[record.policy_source] = sources.get(record.policy_source, 0) + 1
        issue_kinds: dict[str, int] = {}
        for issue in self.issues:
            issue_kinds[issue.kind] = issue_kinds.get(issue.kind, 0) + 1

        return {
            "version": self.version,
            "dataset_hash": self.dataset_hash(),
            "transitions": len(self.records),
            "sessions": len(self.sessions),
            "session_ids": self.sessions,
            "actions": actions,
            "policy_sources": sources,
            "done_transitions": sum(1 for record in self.records if record.done),
            "average_reward": _mean(rewards),
            "total_reward": round(sum(rewards), 4),
            "average_information_gain": _mean(gains),
            "average_steps_per_session": (
                round(len(self.records) / len(self.sessions), 2)
                if self.sessions
                else 0.0
            ),
            "issues": issue_kinds,
            "dropped": self.dropped,
        }


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def validate_transition(record: TransitionRecord) -> list[DatasetIssue]:
    """Every problem that makes one record unusable or suspect."""

    def issue(kind: str, detail: str) -> DatasetIssue:
        return DatasetIssue(
            kind=kind,
            session_id=record.session_id,
            iteration=record.iteration,
            detail=detail,
        )

    issues: list[DatasetIssue] = []

    if record.state() is None:
        issues.append(issue("missing_state", "state_before is missing or unparseable"))
    if not record.action:
        issues.append(issue("missing_action", "action_type is empty"))
    if not math.isfinite(record.reward):
        issues.append(issue("invalid_reward", f"reward is not finite: {record.reward!r}"))
    if record.iteration < 1:
        issues.append(issue("iteration_ordering", f"iteration {record.iteration} < 1"))

    before = record.state()
    after = record.next_state()
    if before is not None and after is not None:
        if after.iteration != before.iteration + 1:
            issues.append(
                issue(
                    "broken_transition",
                    f"next_state.iteration {after.iteration} does not follow "
                    f"state.iteration {before.iteration}",
                )
            )
        if after.session_id != before.session_id:
            issues.append(
                issue(
                    "broken_transition",
                    f"next_state belongs to session {after.session_id!r}, "
                    f"state to {before.session_id!r}",
                )
            )
    elif before is not None and after is None and not record.done:
        issues.append(
            issue(
                "broken_transition",
                "next_state is missing while the transition is not terminal",
            )
        )

    return issues


def build_dataset(
    records: Iterable[TransitionRecord],
    *,
    include_incomplete: bool = False,
    version: str = DATASET_VERSION,
) -> TrajectoryDataset:
    """Order, validate and (unless asked otherwise) drop structurally broken rows.

    Ordering errors and duplicates are always dropped: a broken chain is unusable
    regardless of intent. Whole *sessions* are only included when they end in a
    terminal transition, because training on a truncated run teaches a policy that a
    half-finished investigation is a natural end state.
    """
    ordered = sorted(records, key=lambda item: (item.session_id, item.iteration))
    issues: list[DatasetIssue] = []
    accepted: list[TransitionRecord] = []
    seen: set[tuple[str, int]] = set()
    dropped = 0

    for record in ordered:
        key = (record.session_id, record.iteration)
        if key in seen:
            issues.append(
                DatasetIssue(
                    kind="duplicate_transition",
                    session_id=record.session_id,
                    iteration=record.iteration,
                    detail="two transitions for the same session and iteration",
                )
            )
            dropped += 1
            continue
        seen.add(key)

        found = validate_transition(record)
        # A missing ``next_state`` on a terminal step is expected: the run ended.
        blocking = [
            item for item in found if item.kind != "broken_transition" or not record.done
        ]
        if blocking:
            issues.extend(found)
            dropped += 1
            continue
        issues.extend(found)
        accepted.append(record)

    # Completion filter: keep a session only if its last transition is terminal.
    if not include_incomplete:
        terminal: dict[str, bool] = {}
        for record in accepted:
            terminal[record.session_id] = record.done
        kept = [record for record in accepted if terminal.get(record.session_id)]
        removed_sessions = {
            record.session_id for record in accepted if not terminal.get(record.session_id)
        }
        for session_id in sorted(removed_sessions):
            issues.append(
                DatasetIssue(
                    kind="incomplete_session",
                    session_id=session_id,
                    iteration=0,
                    detail="session has no terminal (done) transition; excluded",
                )
            )
        dropped += len(accepted) - len(kept)
        accepted = kept

    return TrajectoryDataset(
        version=version,
        records=accepted,
        issues=issues,
        dropped=dropped,
    )


def dataset_from_jsonl(raw: str) -> TrajectoryDataset:
    """Rebuild a dataset from an exported JSONL payload (used by tests and tools)."""
    records: list[TransitionRecord] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(TransitionRecord.from_dict(json.loads(line)))
        except (TypeError, ValueError):
            continue
    return build_dataset(records)


def trajectory_is_complete(records: list[TransitionRecord]) -> bool:
    """Whether a session's transitions form an unbroken chain ending in ``done``."""
    if not records:
        return False
    ordered = sorted(records, key=lambda item: item.iteration)
    for previous, current in pairwise(ordered):
        if current.iteration != previous.iteration + 1:
            return False
        before = current.state()
        if (
            before is not None
            and before.previous_action
            and before.previous_action.upper() != previous.action.upper()
        ):
            return False
    return bool(ordered[-1].done) or is_stop(ordered[-1].action)
