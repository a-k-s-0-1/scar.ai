"""Single source of truth for per-depth research limits and coverage targets.

Before this module, depth semantics were duplicated across the orchestrator
(max iterations), the metrics layer (claim targets), the API schema (estimated
duration), and the frontend (depth -> iteration map). Any change to one drifted
from the others silently. Every consumer now reads one profile.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DepthProfile:
    """Limits and coverage targets for one research depth."""

    name: str
    max_iterations: int
    target_claims: int
    target_sources: int
    target_entities: int
    estimated_seconds: int


PROFILES: dict[str, DepthProfile] = {
    "shallow": DepthProfile(
        name="shallow",
        max_iterations=3,
        target_claims=30,
        target_sources=10,
        target_entities=40,
        estimated_seconds=180,
    ),
    "standard": DepthProfile(
        name="standard",
        max_iterations=5,
        target_claims=60,
        target_sources=15,
        target_entities=80,
        estimated_seconds=300,
    ),
    "deep": DepthProfile(
        name="deep",
        max_iterations=8,
        target_claims=120,
        target_sources=25,
        target_entities=160,
        estimated_seconds=480,
    ),
}

DEFAULT_DEPTH = "standard"


def get_depth_profile(depth: str) -> DepthProfile:
    """Return the profile for a depth, falling back to the standard profile."""
    return PROFILES.get(depth, PROFILES[DEFAULT_DEPTH])
