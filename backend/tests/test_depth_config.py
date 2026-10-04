"""Tests for the shared per-depth configuration profiles."""

import pytest

from app.services.depth_config import DEFAULT_DEPTH, PROFILES, get_depth_profile

DOCUMENTED_MAX_ITERATIONS = {"shallow": 3, "standard": 5, "deep": 8}
SCALING_FIELDS = (
    "max_iterations",
    "target_claims",
    "target_sources",
    "target_entities",
    "estimated_seconds",
)


def test_all_depths_have_profiles() -> None:
    """Every depth the API accepts resolves to a profile."""
    assert set(PROFILES) == {"shallow", "standard", "deep"}


@pytest.mark.parametrize(("depth", "max_iterations"), DOCUMENTED_MAX_ITERATIONS.items())
def test_iteration_caps_match_documented_semantics(depth: str, max_iterations: int) -> None:
    """The PRD/memory-doc caps (3/5/8) are the single source of truth."""
    assert get_depth_profile(depth).max_iterations == max_iterations


def test_profiles_scale_monotonically() -> None:
    """Deeper research never has weaker limits or smaller targets."""
    profiles = [get_depth_profile(d) for d in ("shallow", "standard", "deep")]
    for field in SCALING_FIELDS:
        values = [getattr(profile, field) for profile in profiles]
        assert values == sorted(values), f"{field} does not scale with depth"
        assert len(set(values)) == 3, f"{field} is identical across depths"


def test_unknown_depth_falls_back_to_standard() -> None:
    """An unrecognized depth is treated as standard instead of crashing a session."""
    assert get_depth_profile("unlimited").name == DEFAULT_DEPTH
