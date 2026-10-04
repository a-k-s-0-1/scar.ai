"""Judgment Evaluation Vector (JEV) Decision Engine.

Heuristic action selection governing the research loop convergence in V1.
Logs state and reward data for future RL policy replacement.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Decision
from app.database.repository import (
    DecisionRepository,
)
from app.services.metrics import compute_reward_signal
from app.utils.logger import logger

# Tunables for the stopping policy. Gains are novelty-relative (see
# metrics.compute_information_gain), so a plateaued iteration lands well under
# NOVELTY_PLATEAU_GAIN while a productive one stays above it.
NOVELTY_PLATEAU_GAIN = 0.15
DIMINISHING_GAIN = 0.10
COVERAGE_FLOOR = 0.65
CONVERGENCE_COVERAGE = 0.75
WEAK_PLATEAU_COVERAGE = 0.55
MARGINAL_COVERAGE_DELTA = 0.03
PLATEAU_PATIENCE = 3


class ActionType(str, Enum):
    """Actions the research loop orchestrator can select."""

    SEARCH = "SEARCH"
    EXTRACT = "EXTRACT"
    FUSE = "FUSE"
    VERIFY = "VERIFY"
    EXPAND_QUERY = "EXPAND_QUERY"
    STOP = "STOP"


@dataclass
class KnowledgeState:
    """Snapshot of current knowledge base state passed into decision rules.

    Yield fields default to -1, meaning "not reported": stagnation is only inferred
    from measured zeroes, so a caller that does not track per-iteration yield can
    never accidentally trip the stagnation stop.
    """

    iteration: int
    sources_count: int
    claims_count: int
    nodes_count: int
    edges_count: int
    unresolved_contradictions: int
    coverage_estimate: float
    information_gain: float
    gaps: list[str]
    max_iterations: int
    elapsed_time_minutes: float
    max_research_time_minutes: int
    previous_information_gain: float = 1.0
    previous_coverage: float = 0.0
    # Yield of the iteration that just finished (0 means measured zero, -1 unknown).
    new_claims_last_iteration: int = -1
    new_sources_last_iteration: int = -1
    new_nodes_last_iteration: int = -1
    # Consecutive iterations whose information gain stayed below the plateau floor.
    plateau_iterations: int = 0
    # False when the current contradiction set was already verified, which stops the
    # loop from re-running the same verification search forever.
    contradictions_are_new: bool = True
    # Facet cover: mean coverage across the dimensions the question decomposes
    # into, and the dimensions still missing evidence, most valuable first. Empty
    # when the caller does not model facets, which leaves the V1 policy below
    # unchanged.
    facet_coverage: float = 0.0
    facet_gaps: list[str] = field(default_factory=list)


class DecisionEngine:
    """Evaluates session knowledge state and chooses next optimal orchestrator action."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

    def select_action(self, state: KnowledgeState) -> tuple[ActionType, str]:
        """Core JEV heuristic decision policy.

        Returns:
            (selected_action, explanation_reasoning)
        """
        # Hard stop if time limit exceeded
        if state.elapsed_time_minutes >= state.max_research_time_minutes:
            return (
                ActionType.STOP,
                f"Reached maximum allowed research time ({state.max_research_time_minutes} min).",
            )

        # Hard stop if maximum iteration count reached
        if state.iteration >= state.max_iterations:
            return (
                ActionType.STOP,
                f"Reached maximum iteration limit ({state.max_iterations}).",
            )

        # If contradictions are unresolved, are new since the last verification, and we
        # have iterations remaining, verify. Re-verifying an identical pair set only
        # burns an iteration (the search cannot produce anything new), so an already
        # checked set falls through to the plateau checks below.
        if (
            state.unresolved_contradictions > 0
            and state.contradictions_are_new
            and state.iteration < state.max_iterations - 1
        ):
            return (
                ActionType.VERIFY,
                f"Found {state.unresolved_contradictions} unresolved contradiction(s) requiring verification search.",
            )

        # If knowledge coverage is low, continue primary search
        if state.coverage_estimate < COVERAGE_FLOOR:
            return (
                ActionType.SEARCH,
                f"Topic coverage ({int(state.coverage_estimate * 100)}%) is below threshold ({int(COVERAGE_FLOOR * 100)}%). Executing search.",
            )

        # Stagnation: the last iteration produced no new sources, claims or entities. This
        # means search is returning material already covered, so another round would spend
        # model calls for nothing regardless of how high the coverage ratio is.
        if (
            state.iteration >= 2
            and state.new_sources_last_iteration == 0
            and state.new_claims_last_iteration == 0
            and state.new_nodes_last_iteration == 0
        ):
            return (
                ActionType.STOP,
                "No new sources, claims or entities in the last iteration — remaining searches are returning material already covered.",
            )

        # Facet-directed expansion: aggregate coverage can look adequate while a whole
        # dimension of the question has no evidence at all (a viability verdict with no
        # cost evidence is incomplete however many technical claims were found), so the
        # weakest dimension outranks a generic deepening search. Guarded on both facet
        # data and the plateau counter: once the run has plateaued for PLATEAU_PATIENCE
        # iterations, targeting a gap is no longer buying information.
        if (
            state.facet_gaps
            and state.iteration < state.max_iterations - 1
            and state.plateau_iterations < PLATEAU_PATIENCE
        ):
            return (
                ActionType.EXPAND_QUERY,
                (
                    f"Coverage gap in {', '.join(state.facet_gaps[:3])} "
                    f"({int(state.facet_coverage * 100)}% facet coverage). "
                    "Targeting the least-evidenced dimension."
                ),
            )

        # Converge when novelty has plateaued across consecutive iterations and coverage
        # is solid. Checked before gap expansion so a failed corrective attempt can
        # terminate the session; a single low-gain iteration first gets one gap-directed
        # expansion to prove the plateau is real rather than a bad query.
        if (
            state.iteration >= 3
            and state.information_gain < NOVELTY_PLATEAU_GAIN
            and state.previous_information_gain < NOVELTY_PLATEAU_GAIN
            and state.coverage_estimate >= CONVERGENCE_COVERAGE
        ):
            return (
                ActionType.STOP,
                f"Convergence achieved: information gain plateaued ({state.previous_information_gain} -> {state.information_gain}) with {int(state.coverage_estimate * 100)}% coverage.",
            )

        # Diminishing returns on a hard question: coverage never reaches the convergence
        # threshold, but gains have stayed marginal for several iterations and coverage
        # has stopped moving. Continue only while the question is still measurably
        # improving, otherwise the run grinds to the iteration cap for no new evidence.
        if (
            state.iteration >= 3
            and state.plateau_iterations >= PLATEAU_PATIENCE
            and state.information_gain < DIMINISHING_GAIN
            and state.coverage_estimate >= WEAK_PLATEAU_COVERAGE
            and (state.coverage_estimate - state.previous_coverage)
            < MARGINAL_COVERAGE_DELTA
        ):
            gain_floor = int(DIMINISHING_GAIN * 100)
            delta_floor = int(MARGINAL_COVERAGE_DELTA * 100)
            coverage_pct = int(state.coverage_estimate * 100)
            return (
                ActionType.STOP,
                (
                    f"Diminishing returns: information gain stayed below {gain_floor}% "
                    f"for {state.plateau_iterations} iterations and coverage moved "
                    f"less than {delta_floor} points ({coverage_pct}% total)."
                ),
            )

        # If specific gaps have been identified, expand queries
        if state.gaps and state.iteration < state.max_iterations:
            return (
                ActionType.EXPAND_QUERY,
                f"Identified {len(state.gaps)} unexplored knowledge facets. Expanding queries.",
            )

        # Default action
        if state.iteration < state.max_iterations:
            return ActionType.SEARCH, "Deepening evidence base for existing claims."

        return ActionType.STOP, "Completed research cycle."

    async def record_decision(
        self,
        state: KnowledgeState,
        selected_action: ActionType,
        reasoning: str,
        db: AsyncSession,
    ) -> Decision:
        """Persist decision record with snapshot and reward signal."""
        repo = DecisionRepository(db)
        reward = compute_reward_signal(
            information_gain=state.information_gain,
            avg_credibility=0.75,
            unresolved_contradictions=state.unresolved_contradictions,
        )

        decision = await repo.log_decision(
            session_id=self.session_id,
            iteration_number=state.iteration,
            knowledge_state_snapshot=asdict(state),
            available_actions=[a.value for a in ActionType],
            selected_action=selected_action.value,
            action_reasoning=reasoning,
            reward_signal=reward,
        )
        logger.info(
            f"Session {self.session_id} JEV decision #{state.iteration}: {selected_action.value} - {reasoning}"
        )
        return decision
