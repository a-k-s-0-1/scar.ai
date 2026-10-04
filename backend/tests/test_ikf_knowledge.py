"""Tests for IKF 2.0 — entity resolution, temporal windows, versioning and evidence.

The pure modules are tested directly; the service is tested once against the in-memory
database to prove the mapping from ORM rows onto those modules.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import ClaimRepository, SessionRepository, SourceRepository
from app.services.ikf import (
    EntityResolver,
    EvidenceInput,
    SourceRef,
    aggregate_evidence,
    build_knowledge_index,
    build_version_groups,
    evidence_summary,
    extract_validity_window,
    normalize_entity,
    recency_score,
    score_claim,
    temporal_relation,
    values_disagree,
)
from app.services.ikf.claim_versioning import ClaimVersion
from app.services.ikf.temporal import UNKNOWN_DATE_SCORE, UNKNOWN_WINDOW

NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)


def _ref(
    source_id: str,
    *,
    url: str = "",
    source_type: str = "news",
    credibility: float = 0.8,
    days_old: float | None = 30,
    support_type: str = "supports",
    link_confidence: float = 0.8,
) -> SourceRef:
    published = None if days_old is None else NOW - timedelta(days=days_old)
    return SourceRef(
        source_id=source_id,
        url=url or f"https://{source_id}.example.com/story",
        source_type=source_type,
        credibility=credibility,
        published_at=published,
        support_type=support_type,
        link_confidence=link_confidence,
    )


# ─── entity resolution ───────────────────────────────────────────────────────


def test_legal_forms_and_punctuation_collapse_to_one_entity() -> None:
    """Four spellings of OpenAI must produce one node, not four."""
    resolver = EntityResolver()

    canonicals = {
        resolver.resolve("OpenAI"),
        resolver.resolve("OpenAI Inc."),
        resolver.resolve("OpenAI, Inc."),
        resolver.resolve("OpenAI company"),
    }

    assert canonicals == {"OpenAI"}
    assert resolver.stats()["entities"] == 1
    # Normalisation did all the work here — no risky fuzzy merge was needed, which is
    # exactly why the common cases are safe.
    assert resolver.stats()["merges"] == 0
    assert resolver.stats()["aliases_absorbed"] == 3
    # The first spelling seen is the label; every surface form is kept as an alias so
    # provenance can show which wording a claim actually used.
    assert resolver.aliases_for("OpenAI") == [
        "OpenAI",
        "OpenAI Inc.",
        "OpenAI company",
        "OpenAI, Inc.",
    ]


def test_normalization_strips_articles_and_legal_forms() -> None:
    assert normalize_entity("The Acme Corporation") == "acme"
    assert normalize_entity("Acme Ltd") == "acme"
    assert normalize_entity("") == ""


def test_short_labels_never_fuzzy_merge() -> None:
    """Two-character labels are where fuzzy matching becomes a typo generator."""
    resolver = EntityResolver()
    assert resolver.resolve("AI") != resolver.resolve("A1")
    # ...but an exact repeat is still the same entity.
    assert resolver.resolve("AI") == resolver.resolve("ai")
    assert resolver.stats()["entities"] == 2


def test_related_but_distinct_names_stay_apart() -> None:
    """'OpenAI' and 'OpenAI Research' are not the same node."""
    resolver = EntityResolver()
    assert resolver.resolve("OpenAI") != resolver.resolve("OpenAI Research")


def test_seeded_aliases_let_memory_teach_acronyms() -> None:
    """Acronyms cannot be inferred; long-term memory has to supply them."""
    resolver = EntityResolver()
    resolver.seed({"IBM": ["Big Blue", "International Business Machines"]})

    assert resolver.resolve("big blue") == "IBM"
    assert resolver.resolve("International Business Machines") == "IBM"
    assert resolver.stats()["merges"] == 0  # seeding is not a merge


def test_alias_table_is_exportable_for_memory() -> None:
    resolver = EntityResolver()
    resolver.resolve("OpenAI")
    resolver.resolve("OpenAI Inc.")

    assert resolver.alias_table() == {"OpenAI": ["OpenAI", "OpenAI Inc."]}


# ─── temporal ────────────────────────────────────────────────────────────────


def test_extract_validity_window_variants() -> None:
    assert extract_validity_window("between 2019 and 2021").start == 2019
    assert extract_validity_window("between 2019 and 2021").end == 2021
    assert extract_validity_window("since 2020").start == 2020
    assert extract_validity_window("since 2020").end is None
    assert extract_validity_window("by 2030").end == 2030
    assert extract_validity_window("Q3 2025").precision == "quarter"
    assert extract_validity_window("March 2024").precision == "month"
    assert extract_validity_window("revenue grew in 2023").year == 2023
    # A range must win over the lone years inside it.
    assert extract_validity_window("between 2019 and 2021").start == 2019


def test_undated_claim_falls_back_then_reports_unknown() -> None:
    assert extract_validity_window("no dates here").known is False
    assert extract_validity_window("no dates here", fallback_year=2024).year == 2024


def test_recency_decays_with_age_and_clamps() -> None:
    fresh = recency_score(NOW - timedelta(days=1), now=NOW)
    year_old = recency_score(NOW - timedelta(days=365), now=NOW)
    ancient = recency_score(NOW - timedelta(days=4_000), now=NOW)

    assert fresh > year_old > ancient
    assert recency_score(None, now=NOW) == UNKNOWN_DATE_SCORE
    # A future-dated source clamps instead of exceeding the ceiling.
    assert recency_score(NOW + timedelta(days=10), now=NOW) <= 1.0


def test_temporal_relation_classifies_order_and_concurrency() -> None:
    old = extract_validity_window("in 2024")
    new = extract_validity_window("in 2026")
    same = extract_validity_window("as of 2024")

    assert temporal_relation(old, new) == "right_newer"
    assert temporal_relation(new, old) == "left_newer"
    assert temporal_relation(old, same) == "same"
    assert temporal_relation(old, UNKNOWN_WINDOW) == "unknown"


# ─── claim versioning ────────────────────────────────────────────────────────


def _version(
    claim_id: str,
    value: str,
    *,
    year: int | None,
    predicate: str = "market_share",
    subject: str = "openai",
) -> ClaimVersion:
    return ClaimVersion(
        claim_id=claim_id,
        text=f"{subject} {predicate} {value}",
        subject=subject,
        predicate=predicate,
        value=value,
        window=extract_validity_window(str(year) if year else ""),
        extracted_at=NOW,
    )


def test_same_fact_at_two_dates_is_versioned_not_conflicted() -> None:
    """65% in 2024 and 71% in 2026 is the fact moving, not sources disagreeing."""
    groups = build_version_groups(
        [_version("a", "65%", year=2024), _version("b", "71%", year=2026)]
    )

    assert len(groups) == 1
    group = groups[0]
    assert group.status == "versioned"
    assert group.conflicts == []
    assert group.span == (2024, 2026)
    # Newest first, so the reader leads with the current number.
    assert group.latest is not None and group.latest.claim_id == "b"


def test_same_period_different_values_is_a_conflict() -> None:
    groups = build_version_groups(
        [_version("a", "65%", year=2024), _version("b", "71%", year=2024)]
    )

    assert groups[0].status == "conflicted"
    assert groups[0].conflicts == [("a", "b")]


def test_numeric_tolerance_absorbs_rounding() -> None:
    assert values_disagree("71%", "71.0%") is False
    assert values_disagree("71%", "71.4%") is False
    assert values_disagree("65%", "71%") is True


def test_absent_values_and_restatements_never_conflict() -> None:
    assert values_disagree("", "71%") is False
    assert values_disagree("a major exporter", "a major exporter ") is False

    groups = build_version_groups(
        [_version("a", "", year=2024), _version("b", "", year=2024)]
    )
    assert groups[0].status == "single"


def test_version_group_prefers_the_strongest_evidence_when_values_disagree() -> None:
    weak = _version("weak", "50%", year=2024)
    weak.strength = 0.2
    strong = _version("strong", "80%", year=2024)
    strong.strength = 0.9

    group = build_version_groups([weak, strong])[0]
    assert group.strongest is not None and group.strongest.claim_id == "strong"


# ─── evidence strength ───────────────────────────────────────────────────────


def test_bands_match_the_documented_worked_examples() -> None:
    """The three examples in evidence.py's docstring, held to their stated bands."""
    strong = score_claim(
        EvidenceInput(
            claim_id="strong",
            refs=[
                _ref(f"gov{i}", source_type="government", credibility=0.95, days_old=30)
                for i in range(4)
            ],
            extraction_confidence="high",
            now=NOW,
        )
    )
    middling = score_claim(
        EvidenceInput(
            claim_id="middling",
            refs=[
                _ref("news1", url="https://a.example.com/x", days_old=180),
                _ref("news2", url="https://b.example.com/y", days_old=180),
            ],
            extraction_confidence="medium",
            now=NOW,
        )
    )
    weak = score_claim(
        EvidenceInput(
            claim_id="weak",
            refs=[
                _ref(
                    "blog",
                    source_type="blog",
                    credibility=0.4,
                    days_old=730,
                )
            ],
            extraction_confidence="medium",
            now=NOW,
        )
    )

    assert strong.band == "high" and strong.strength > 0.8
    assert middling.band == "medium" and 0.3 <= middling.strength < 0.6
    assert weak.band == "low" and weak.strength < 0.15


def test_independent_support_and_refutation_move_the_score() -> None:
    same_domain = [
        _ref("a", url="https://wire.example.com/1"),
        _ref("b", url="https://wire.example.com/2"),
    ]
    different_domains = [
        _ref("c", url="https://first.example.com/1"),
        _ref("d", url="https://second.example.com/2"),
    ]

    syndicated = score_claim(
        EvidenceInput(claim_id="s", refs=same_domain, now=NOW)
    )
    independent = score_claim(
        EvidenceInput(claim_id="i", refs=different_domains, now=NOW)
    )

    # Two copies of one wire story must not count as two sources.
    assert syndicated.provenance is not None
    assert syndicated.provenance.independent_sources == 1
    assert independent.provenance is not None
    assert independent.provenance.independent_sources == 2
    assert independent.strength > syndicated.strength

    refuted = score_claim(
        EvidenceInput(
            claim_id="r",
            refs=[
                _ref("s1", url="https://one.example.com/x"),
                _ref("s2", url="https://two.example.com/y", support_type="refutes"),
            ],
            now=NOW,
        )
    )
    assert refuted.components["agreement"] == 0.5
    assert refuted.strength < independent.strength


def test_undated_sources_are_neutral_not_stale() -> None:
    undated = score_claim(
        EvidenceInput(claim_id="u", refs=[_ref("x", days_old=None)], now=NOW)
    )
    assert undated.components["recency"] == UNKNOWN_DATE_SCORE


def test_aggregate_and_summary_report_bands_and_extremes() -> None:
    scores = aggregate_evidence(
        [
            EvidenceInput(
                claim_id="best",
                refs=[
                    _ref(f"g{i}", source_type="government", credibility=0.95)
                    for i in range(3)
                ],
                extraction_confidence="high",
                now=NOW,
            ),
            EvidenceInput(
                claim_id="worst",
                refs=[_ref("b", source_type="social", credibility=0.2, days_old=900)],
                extraction_confidence="low",
                now=NOW,
            ),
        ]
    )

    assert [score.claim_id for score in scores] == ["best", "worst"]
    summary = evidence_summary(scores)
    assert summary["claims"] == 2
    assert summary["strongest_claim_id"] == "best"
    assert summary["weakest_claim_id"] == "worst"
    assert summary["high"] == 1 and summary["low"] == 1


# ─── service: ORM → index ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_knowledge_index_scores_claims_and_groups_versions(
    db_session: AsyncSession,
) -> None:
    """The service maps stored rows onto resolution, evidence and versioning."""
    sessions = SessionRepository(db_session)
    sources = SourceRepository(db_session)
    claims = ClaimRepository(db_session)

    session = await sessions.create(question="How big is the solid-state battery market?")

    strong_source = await sources.create(
        session_id=session.id,
        url="https://energy.gov/report",
        title="National battery review",
        content="...",
        source_type="government",
        credibility_score=0.95,
        published_at=NOW - timedelta(days=20),
    )
    weak_source = await sources.create(
        session_id=session.id,
        url="https://forum.example.com/thread",
        title="Forum thread",
        content="...",
        source_type="forum",
        credibility_score=0.3,
        published_at=NOW - timedelta(days=900),
    )

    # Two readings of the same metric, a year apart: versioning, not a fight.
    early = await claims.create(
        session_id=session.id,
        claim_text="Solid-state battery share was 4% in 2024.",
        subject="Solid-state battery market",
        predicate="share_of",
        obj="4%",
        confidence="high",
    )
    latest = await claims.create(
        session_id=session.id,
        claim_text="Solid-state battery share is 9% in 2025.",
        subject="Solid-State Battery Market Inc.",
        predicate="share_of",
        obj="9%",
        confidence="high",
    )
    await claims.link_source(early.id, strong_source.id)
    await claims.link_source(latest.id, weak_source.id)
    await db_session.commit()

    index = await build_knowledge_index(session.id, db_session, now=NOW)

    assert index.evidence_stats["claims"] == 2
    # A single source cannot reach "high" however good it is: the independence factor
    # tops out at ~0.61 for one publisher, so corroboration is what unlocks the band.
    assert index.band_of(early.id) == "medium"
    assert index.band_of(latest.id) == "low"
    assert index.strength_of(early.id) > index.strength_of(latest.id)

    # Both subjects resolve to one canonical entity, so the two rows group together.
    assert index.resolver.stats()["entities"] == 1
    assert len(index.groups) == 1
    assert index.groups[0].status == "versioned"
    assert index.groups[0].span == (2024, 2025)
    assert index.conflicted_pairs() == []
    assert index.versioned_claim_ids() == {early.id, latest.id}

    summary = index.to_summary()
    assert summary["versions"]["versioned"] == 1


@pytest.mark.asyncio
async def test_seeded_aliases_from_memory_are_honoured(db_session: AsyncSession) -> None:
    sessions = SessionRepository(db_session)
    claims = ClaimRepository(db_session)

    session = await sessions.create(question="Who leads the market?")
    await claims.create(
        session_id=session.id,
        claim_text="Big Blue still leads.",
        subject="Big Blue",
        predicate="leads",
        obj="the market",
        confidence="medium",
    )
    await db_session.commit()

    index = await build_knowledge_index(
        session.id,
        db_session,
        seed_aliases={"IBM": ["Big Blue"]},
    )

    assert index.resolver.resolve("Big Blue") == "IBM"
    assert index.groups[0].subject == "IBM"
