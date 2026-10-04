"""Formal action space (V2 2.2).

V1's ``ActionType`` (``SEARCH``, ``VERIFY``, ``EXPAND_QUERY``, ``STOP``) stays exactly
as it is — the live loop, the decision log and every existing test depend on it. What
V2 needs is a *policy* action space that can grow without a second migration every
time an action is added, plus an explicit statement of which actions the orchestrator
can actually execute.

The rule enforced here: **an action is in the policy space only if the orchestrator
can execute it.** The richer search variants (``SEARCH_NEW_FACET``,
``SEARCH_PRIMARY_SOURCE``, ``SEARCH_COUNTER_EVIDENCE``, …) are declared with
``executable=False`` so the offline policy can never recommend something the loop
would silently ignore; when the orchestrator learns to run one, flipping the flag is
the whole change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.services.decision_engine import ActionType as JevActionType


class PolicyAction(str, Enum):
    """Actions a research policy may select.

    The first four are V1's live actions and the only ones currently executable. The
    rest are declared so datasets, policies and dashboards can carry them the day the
    orchestrator supports them.
    """

    SEARCH = "SEARCH"
    VERIFY = "VERIFY"
    EXPAND_QUERY = "EXPAND_QUERY"
    STOP = "STOP"
    # Declared, not yet executable.
    SEARCH_NEW_FACET = "SEARCH_NEW_FACET"
    SEARCH_PRIMARY_SOURCE = "SEARCH_PRIMARY_SOURCE"
    SEARCH_RECENT_SOURCE = "SEARCH_RECENT_SOURCE"
    SEARCH_COUNTER_EVIDENCE = "SEARCH_COUNTER_EVIDENCE"
    COMPARE_SOURCES = "COMPARE_SOURCES"
    REVISIT_WEAK_CLAIM = "REVISIT_WEAK_CLAIM"


#: Tie-break order when action values are equal. It is JEV's own preference order,
#: so a policy that has learned nothing yet behaves like the baseline rather than
#: like a coin flip.
ACTION_PRIORITY: list[str] = [
    PolicyAction.VERIFY.value,
    PolicyAction.EXPAND_QUERY.value,
    PolicyAction.SEARCH.value,
    PolicyAction.STOP.value,
]


@dataclass(frozen=True)
class ActionSpec:
    """Everything the system needs to know about one action.

    ``parameters`` names the keys the action accepts, and ``required`` the subset it
    must carry to be valid. ``jev_equivalent`` maps the action back onto the live JEV
    vocabulary; ``None`` means the orchestrator cannot execute it yet.
    """

    action: PolicyAction
    executable: bool
    description: str
    parameters: tuple[str, ...] = ()
    required: tuple[str, ...] = ()
    jev_equivalent: str | None = None
    #: Relative cost in "action units"; used by the evaluation engine's cost metric.
    cost_weight: float = 1.0

    @property
    def value(self) -> str:
        return self.action.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "executable": self.executable,
            "description": self.description,
            "parameters": list(self.parameters),
            "required": list(self.required),
            "jev_equivalent": self.jev_equivalent,
            "cost_weight": self.cost_weight,
        }


ACTION_SPECS: dict[str, ActionSpec] = {
    PolicyAction.SEARCH.value: ActionSpec(
        action=PolicyAction.SEARCH,
        executable=True,
        description="Run a broad search to widen the evidence base.",
        parameters=("query", "facet", "max_results"),
        required=(),
        jev_equivalent=JevActionType.SEARCH.value,
        cost_weight=1.0,
    ),
    PolicyAction.VERIFY.value: ActionSpec(
        action=PolicyAction.VERIFY,
        executable=True,
        description="Search for evidence for or against a conflicting claim.",
        parameters=("claim_id", "query"),
        required=(),
        jev_equivalent=JevActionType.VERIFY.value,
        cost_weight=1.0,
    ),
    PolicyAction.EXPAND_QUERY.value: ActionSpec(
        action=PolicyAction.EXPAND_QUERY,
        executable=True,
        description="Target a specific coverage gap with a refined query.",
        parameters=("gap", "facet", "query"),
        required=(),
        jev_equivalent=JevActionType.EXPAND_QUERY.value,
        cost_weight=1.0,
    ),
    PolicyAction.STOP.value: ActionSpec(
        action=PolicyAction.STOP,
        executable=True,
        description="End the run: further research is no longer worth its cost.",
        parameters=("reason",),
        required=(),
        jev_equivalent=JevActionType.STOP.value,
        cost_weight=0.0,
    ),
    PolicyAction.SEARCH_NEW_FACET.value: ActionSpec(
        action=PolicyAction.SEARCH_NEW_FACET,
        executable=False,
        description="Search a dimension of the question with no evidence at all.",
        parameters=("facet", "query"),
        required=("facet",),
        jev_equivalent=None,
        cost_weight=1.0,
    ),
    PolicyAction.SEARCH_PRIMARY_SOURCE.value: ActionSpec(
        action=PolicyAction.SEARCH_PRIMARY_SOURCE,
        executable=False,
        description="Prefer primary sources (papers, filings, datasets).",
        parameters=("query",),
        required=("query",),
        jev_equivalent=None,
        cost_weight=1.1,
    ),
    PolicyAction.SEARCH_RECENT_SOURCE.value: ActionSpec(
        action=PolicyAction.SEARCH_RECENT_SOURCE,
        executable=False,
        description="Prefer recent sources for a fast-moving fact.",
        parameters=("query",),
        required=("query",),
        jev_equivalent=None,
        cost_weight=1.0,
    ),
    PolicyAction.SEARCH_COUNTER_EVIDENCE.value: ActionSpec(
        action=PolicyAction.SEARCH_COUNTER_EVIDENCE,
        executable=False,
        description="Deliberately seek disconfirming evidence.",
        parameters=("claim_id", "query"),
        required=(),
        jev_equivalent=None,
        cost_weight=1.0,
    ),
    PolicyAction.COMPARE_SOURCES.value: ActionSpec(
        action=PolicyAction.COMPARE_SOURCES,
        executable=False,
        description="Compare two sources that assert different values.",
        parameters=("source_ids",),
        required=("source_ids",),
        jev_equivalent=None,
        cost_weight=0.5,
    ),
    PolicyAction.REVISIT_WEAK_CLAIM.value: ActionSpec(
        action=PolicyAction.REVISIT_WEAK_CLAIM,
        executable=False,
        description="Re-check a claim whose evidence strength is low.",
        parameters=("claim_id",),
        required=("claim_id",),
        jev_equivalent=None,
        cost_weight=0.5,
    ),
}


def executable_actions() -> list[str]:
    """Action values the orchestrator can actually run, in stable priority order."""
    declared = [spec.value for spec in ACTION_SPECS.values() if spec.executable]
    ordered = [value for value in ACTION_PRIORITY if value in declared]
    return ordered + sorted(set(declared) - set(ordered))


def all_action_values() -> list[str]:
    """Every declared action, executable or not (for datasets and dashboards)."""
    return list(ACTION_SPECS)


def action_spec(action: str | PolicyAction) -> ActionSpec:
    """Look up one action's specification, raising on an unknown value."""
    value = action.value if isinstance(action, PolicyAction) else str(action).upper()
    spec = ACTION_SPECS.get(value)
    if spec is None:
        raise ValueError(f"Unknown research action '{action}'.")
    return spec


def is_executable(action: str | PolicyAction) -> bool:
    return action_spec(action).executable


def is_stop(action: str | PolicyAction) -> bool:
    value = action.value if isinstance(action, PolicyAction) else str(action).upper()
    return value == PolicyAction.STOP.value


def to_jev_action(action: str | PolicyAction) -> JevActionType | None:
    """Map a policy action onto the live JEV action, or ``None`` if unsupported."""
    equivalent = action_spec(action).jev_equivalent
    return JevActionType(equivalent) if equivalent else None


def from_jev_action(action: JevActionType | str) -> PolicyAction | None:
    """Map the live JEV action onto the policy space.

    ``EXTRACT``/``FUSE`` are V1 loop stages that JEV never selects; they map to no
    policy action rather than being silently coerced into SEARCH.
    """
    value = action.value if isinstance(action, JevActionType) else str(action).upper()
    for spec in ACTION_SPECS.values():
        if spec.jev_equivalent == value:
            return spec.action
    return None


@dataclass(frozen=True)
class ActionRequest:
    """One concrete action with its parameters — what a transition stores.

    Validation is deliberately strict at construction: a transition whose action
    cannot be executed is a bug in the collector, not a data point.
    """

    action: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        spec = action_spec(self.action)
        object.__setattr__(self, "action", spec.action.value)
        missing = [key for key in spec.required if not self.parameters.get(key)]
        if missing:
            raise ValueError(
                f"Action {spec.action.value} is missing required parameter(s): "
                f"{', '.join(missing)}."
            )

    @property
    def spec(self) -> ActionSpec:
        return action_spec(self.action)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action,
            "parameters": {k: v for k, v in self.parameters.items() if v is not None},
            "executable": self.spec.executable,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> ActionRequest | None:
        """Rebuild an action from stored JSON, or ``None`` when it is unusable."""
        if not payload:
            return None
        raw_action = payload.get("action_type") or payload.get("action")
        if not raw_action:
            return None
        try:
            return cls(action=str(raw_action), parameters=payload.get("parameters") or {})
        except ValueError:
            return None


def executable_action_request(action: str, parameters: dict[str, Any] | None = None) -> ActionRequest:
    """Build an action request and assert it is one the loop can run."""
    request = ActionRequest(action=action, parameters=parameters or {})
    if not request.spec.executable:
        raise ValueError(f"Action {request.action} is declared but not executable yet.")
    return request
