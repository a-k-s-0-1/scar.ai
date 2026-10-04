"""Metrics and reward signal computation for tracking research quality and reinforcement learning."""

import math

from app.services.depth_config import get_depth_profile

# Coverage approaches (but never reaches) 1.0. Calibrated so that exactly meeting
# every depth target yields ~0.80 coverage, the PRD's canonical stop threshold,
# while still showing meaningful movement before and after that point.
_COVERAGE_SATURATION_K = 1.6
_COVERAGE_WEIGHTS = {"claims": 0.45, "sources": 0.25, "entities": 0.30}


def compute_information_gain(
    previous_claims_count: int,
    current_claims_count: int,
    new_unique_entities: int,
    existing_entities: int = 0,
) -> float:
    """Calculate normalized information gain metric (0.0 to 1.0) for an iteration.

    Gain is measured as novelty relative to what is already known: the share of the
    current claim corpus that is new, blended with the share of the knowledge graph
    that is new. Normalizing against the accumulated corpus (instead of a fixed
    per-iteration constant) keeps the signal informative as the session grows;
    fixed constants saturate to 1.0 once iteration yield exceeds them, which makes
    plateau detection unreachable.
    """
    delta_claims = max(0, current_claims_count - previous_claims_count)
    if previous_claims_count == 0:
        return 1.0 if delta_claims > 0 else 0.0

    claim_novelty = delta_claims / max(1, current_claims_count)
    total_entities = existing_entities + new_unique_entities
    entity_novelty = new_unique_entities / max(1, total_entities)

    return round(0.6 * claim_novelty + 0.4 * entity_novelty, 3)


def saturate_coverage(weighted_ratio: float) -> float:
    """Map an unbounded evidence ratio onto the shared asymptotic coverage curve.

    The aggregate coverage metric and the per-facet coverage model share one
    curve, so "target met" means the same thing for a single dimension of a
    question as it does for the session as a whole. Ratios are never capped:
    capping pins the metric at 1.0 as soon as one target is exceeded, which makes
    it blind exactly when the evidence is richest.
    """
    return round(1.0 - math.exp(-_COVERAGE_SATURATION_K * weighted_ratio), 3)


def compute_coverage_estimate(
    claims_count: int,
    sources_count: int,
    min_sources_required: int,
    depth: str = "standard",
    nodes_count: int = 0,
) -> float:
    """Estimate knowledge coverage against the depth profile's targets.

    Blends claim density, source diversity, and knowledge-graph richness, then
    maps the weighted ratio through the shared saturation curve.
    """
    profile = get_depth_profile(depth)
    target_sources = max(profile.target_sources, min_sources_required)

    weighted_ratio = (
        _COVERAGE_WEIGHTS["claims"] * claims_count / max(1, profile.target_claims)
        + _COVERAGE_WEIGHTS["sources"] * sources_count / max(1, target_sources)
        + _COVERAGE_WEIGHTS["entities"] * nodes_count / max(1, profile.target_entities)
    )

    return saturate_coverage(weighted_ratio)


def compute_reward_signal(
    information_gain: float,
    avg_credibility: float,
    unresolved_contradictions: int,
    action_cost: float = 0.05,
) -> float:
    """Compute scalar reward signal logged for each iteration decision.

    Reward = information_gain * 2.0 + avg_credibility - (contradictions * 0.4) - action_cost
    """
    reward = (
        (information_gain * 2.0)
        + (avg_credibility * 1.0)
        - (unresolved_contradictions * 0.4)
        - action_cost
    )
    return round(reward, 4)
