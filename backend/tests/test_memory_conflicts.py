"""Memory update rules (V2 2.12): supersede, conflict, verify — never overwrite."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.memory import (
    STATUS_ACTIVE,
    STATUS_CONFLICTING,
    STATUS_NEEDS_VERIFICATION,
    STATUS_SUPERSEDED,
    ClaimVersionRecord,
    LongTermMemory,
    conflict_report,
    group_status,
    merge_versions,
    version_statuses,
)


def _version(value: str, year: int | None, session: str = "s1", **extra) -> ClaimVersionRecord:
    return ClaimVersionRecord(
        value=value,
        text=extra.pop("text", f"Value was {value}."),
        valid_from=year,
        valid_to=year,
        session_id=session,
        sources=extra.pop("sources", (f"https://{session}.example",)),
        confidence=extra.pop("confidence", 0.7),
        **extra,
    )


def _stored(*versions: ClaimVersionRecord) -> list[dict]:
    merged: list[dict] = []
    for version in versions:
        merged = merge_versions(merged, version)
    return merged


def test_relearning_the_same_observation_updates_instead_of_duplicating() -> None:
    first = _version("$4/kg", 2024)
    again = ClaimVersionRecord(
        value="$4/kg",
        text="$4/kg in 2024.",
        valid_from=2024,
        valid_to=2024,
        session_id="s1",
        sources=("https://new.example",),
    )

    merged = merge_versions(_stored(first), again)

    assert len(merged) == 1
    assert merged[0]["sources"] == ["https://new.example"]


def test_a_moved_fact_keeps_both_readings_with_statuses() -> None:
    merged = _stored(_version("$4/kg", 2024, session="old"), _version("$2/kg", 2026))

    statuses = version_statuses(merged)

    assert statuses[0] == STATUS_ACTIVE  # newest first
    assert statuses[1] == STATUS_SUPERSEDED
    assert group_status(merged) == STATUS_SUPERSEDED
    report = conflict_report(merged)
    assert report["current"]["value"] == "$2/kg"
    assert report["superseded"][0]["value"] == "$4/kg"
    assert report["conflicts"] == []


def test_same_period_different_values_is_a_conflict_not_a_version() -> None:
    merged = _stored(_version("$4/kg", 2026, session="a"), _version("$2/kg", 2026, session="b"))

    report = conflict_report(merged)

    assert report["status"] == STATUS_CONFLICTING
    assert {version["status"] for version in report["versions"]} == {
        STATUS_CONFLICTING
    }
    assert len(report["conflicts"]) == 1
    conflict = report["conflicts"][0]
    assert {conflict["old"]["value"], conflict["new"]["value"]} == {"$4/kg", "$2/kg"}
    assert "same period" in conflict["reason"]


def test_a_rounded_restatement_is_not_a_conflict() -> None:
    merged = _stored(_version("71%", 2026), _version("71.4%", 2026))

    assert version_statuses(merged)[0] == STATUS_ACTIVE
    assert group_status(merged) == STATUS_SUPERSEDED


def test_undated_readings_are_flagged_for_verification_not_ordered() -> None:
    merged = _stored(_version("$4/kg", None), _version("$2/kg", None))

    statuses = version_statuses(merged)

    assert STATUS_NEEDS_VERIFICATION in statuses
    assert group_status(merged) == STATUS_NEEDS_VERIFICATION


def test_a_single_reading_is_active() -> None:
    merged = _stored(_version("$4/kg", 2026))

    assert version_statuses(merged) == [STATUS_ACTIVE]
    assert group_status(merged) == STATUS_ACTIVE


def test_versions_are_capped_newest_first() -> None:
    merged = _stored(*[_version(f"${value}/kg", 2000 + value) for value in range(1, 15)])

    assert len(merged) == 8
    assert merged[0]["valid_from"] == 2014


def test_version_statuses_never_contradict_the_conflict_report() -> None:
    merged = _stored(
        _version("$4/kg", 2026, session="a"),
        _version("$2/kg", 2026, session="b"),
        _version("$3/kg", 2025, session="c"),
    )

    report = conflict_report(merged)

    assert report["status"] == STATUS_CONFLICTING
    assert all("status" in version for version in report["versions"])


# ─── service level ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_new_research_supersedes_an_older_remembered_claim(
    db_session: AsyncSession, memory_bound_to_test_db: None
) -> None:
    memory = LongTermMemory()

    await memory.remember_claim_versions(
        [
            {
                "subject": "hydrogen cost",
                "predicate": "equals",
                "versions": [_version("$4/kg", 2024, session="run-2024")],
            }
        ],
        session_id="run-2024",
    )
    # The same fact observed once more, a year later: it must not overwrite the old
    # reading, it must version it.
    await memory.remember_claim_versions(
        [
            {
                "subject": "hydrogen cost",
                "predicate": "equals",
                "versions": [_version("$2/kg", 2026, session="run-2026")],
            }
        ],
        session_id="run-2026",
    )

    items = await memory.versioned_claims()

    assert len(items) == 1
    item = items[0]
    assert item["status"] == STATUS_SUPERSEDED
    assert [version["value"] for version in item["versions"]] == ["$2/kg", "$4/kg"]
    assert {version["session_id"] for version in item["versions"]} == {
        "run-2024",
        "run-2026",
    }
    assert all(version["sources"] for version in item["versions"])
    assert all(version["recorded_at"] for version in item["versions"])


@pytest.mark.asyncio
async def test_conflicting_research_is_remembered_as_conflicting(
    db_session: AsyncSession, memory_bound_to_test_db: None
) -> None:
    memory = LongTermMemory()

    await memory.remember_claim_versions(
        [
            {
                "subject": "solid state market share",
                "predicate": "equals",
                "versions": [_version("71%", 2026, session="source-a")],
            }
        ],
        session_id="source-a",
    )
    await memory.remember_claim_versions(
        [
            {
                "subject": "solid state market share",
                "predicate": "equals",
                "versions": [_version("12%", 2026, session="source-b")],
            }
        ],
        session_id="source-b",
    )

    conflicts = await memory.versioned_claims(statuses=[STATUS_CONFLICTING])

    assert len(conflicts) == 1
    assert conflicts[0]["conflicts"] == 1
    assert conflicts[0]["report"]["conflicts"][0]["reason"]


@pytest.mark.asyncio
async def test_a_lone_observation_is_stored_once_and_bounded(
    db_session: AsyncSession, memory_bound_to_test_db: None
) -> None:
    """A first observation must exist for a later run to supersede — but only once."""
    memory = LongTermMemory()

    summary = await memory.remember_claim_versions(
        [
            {
                "subject": "one-off fact",
                "predicate": "states",
                "versions": [_version("something", 2026)],
            }
        ],
        session_id="run-1",
    )

    assert summary.updated_facts == 1
    assert summary.new_facts == 1
    items = await memory.versioned_claims()
    assert len(items) == 1
    assert items[0]["status"] == STATUS_ACTIVE
    assert len(items[0]["versions"]) == 1

    # Learning the same fact again must not create a second row.
    await memory.remember_claim_versions(
        [
            {
                "subject": "one-off fact",
                "predicate": "states",
                "versions": [_version("something", 2026, session="run-2")],
            }
        ],
        session_id="run-2",
    )
    assert len(await memory.versioned_claims()) == 1


@pytest.mark.asyncio
async def test_session_items_carry_provenance(
    db_session: AsyncSession, memory_bound_to_test_db: None
) -> None:
    memory = LongTermMemory()
    await memory.remember_claim_versions(
        [
            {
                "subject": "cost",
                "predicate": "equals",
                "versions": [
                    _version("$4/kg", 2024, session="run-1"),
                    _version("$2/kg", 2026, session="run-1"),
                ],
            }
        ],
        session_id="run-1",
    )

    items = await memory.items_for_session("run-1")

    assert len(items) == 1
    provenance = items[0]["provenance"]
    assert provenance["session_id"] == "run-1"
    assert provenance["status"] == STATUS_SUPERSEDED
    assert provenance["created_at"]
    assert provenance["last_verified_at"]
