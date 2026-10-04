"""Report Generator compiling final executive summary, evidence table, citations, and unresolved unknowns."""

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import (
    ClaimRepository,
    ContradictionRepository,
    KnowledgeRepository,
    SessionRepository,
    SourceRepository,
)
from app.integrations.llm_router import TaskType, llm_router
from app.services.ikf import (
    EntityResolver,
    aggregate_evidence,
    build_claim_versions,
    build_evidence_inputs,
    build_version_groups,
    evidence_summary,
    versioning_summary,
)
from app.services.metrics import compute_coverage_estimate
from app.utils.logger import logger

# How many times a finished report may be re-synthesized. Each attempt is one
# model call over evidence already gathered, so the cap only exists to stop a
# retry loop from spending a session's budget on a provider that is down.
MAX_SYNTHESIS_RETRIES = 3

# One re-synthesis at a time per session. Two concurrent retries both read the same
# attempt count, both spend a model call, and both write the same increment, so the
# counter stands still while the budget drains and the retry cap can be walked past.
# In-process, like the rate limiter and the running-session registry: this is a
# single-node dev server, and the failure mode of the registry is only memory.
_synthesis_locks: dict[str, asyncio.Lock] = {}


def synthesis_lock(session_id: str) -> asyncio.Lock:
    """Return the lock that serialises report rewrites for one session."""
    lock = _synthesis_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _synthesis_locks[session_id] = lock
    return lock

REPORT_SYNTHESIS_SYSTEM = """You are an elite research synthesis analyst.
Your objective is to produce an authoritative, nuanced, and strictly evidence-grounded final research report based ONLY on the provided claims and sources.
Requirements:
1. Executive Summary: 2-3 precise, high-density sentences answering the question directly.
2. Key Findings: 3-6 distinct thematic bullet points synthesizing empirical evidence.
3. Unknowns / Gaps: 2-3 aspects that remain unproven, ambiguous, or poorly evidenced.
4. Output valid JSON only with keys: "executive_summary", "key_findings", "unknowns".
"""


class ReportGenerator:
    """Assembles final comprehensive research report and stores it in session records."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

    async def generate_report(
        self,
        db: AsyncSession,
        *,
        retry_count: int = 0,
        mark_completed: bool = True,
    ) -> dict[str, Any]:
        """Compile full research report from all persisted session artifacts.

        ``retry_count`` records how many one-click re-syntheses this report has
        already had, and ``mark_completed=False`` rewrites the report of an
        already-finished run without touching its status.
        """
        session_repo = SessionRepository(db)
        source_repo = SourceRepository(db)
        claim_repo = ClaimRepository(db)
        contra_repo = ContradictionRepository(db)
        know_repo = KnowledgeRepository(db)

        session = await session_repo.get_by_id(self.session_id)
        if not session:
            raise ValueError(f"Session '{self.session_id}' not found.")

        sources = await source_repo.get_by_session(self.session_id)
        claims = await claim_repo.get_by_session(self.session_id)
        contradictions = await contra_repo.get_by_session(self.session_id)
        nodes, edges = await know_repo.get_graph(self.session_id)

        # IKF 2.0 is derived here from the rows already loaded above rather than
        # re-queried: evidence strength and claim versioning must describe exactly
        # the claims in this report, and a second read could disagree with it.
        resolver = EntityResolver()
        evidence_scores = aggregate_evidence(build_evidence_inputs(claims))
        evidence_by_id = {score.claim_id: score for score in evidence_scores}
        version_groups = build_version_groups(
            build_claim_versions(claims, evidence_by_id, resolver)
        )
        evidence_stats = evidence_summary(evidence_scores)
        version_stats = versioning_summary(version_groups)

        # Build citations mapping
        citations = []
        source_id_to_idx = {}
        for idx, src in enumerate(sources, 1):
            source_id_to_idx[src.id] = idx
            citations.append(
                {
                    "citation_number": idx,
                    "source_id": src.id,
                    "url": src.url,
                    "title": src.title or src.url,
                    "credibility_score": src.credibility_score,
                    "published_at": (
                        src.published_at.isoformat() if src.published_at else None
                    ),
                }
            )

        # Build evidence items with citations
        evidence_items = []
        for claim in claims:
            linked_citations = []
            for link in getattr(claim, "source_links", []):
                s_id = link.source_id
                if s_id in source_id_to_idx:
                    linked_citations.append(source_id_to_idx[s_id])

            score = evidence_by_id.get(claim.id)
            evidence_items.append(
                {
                    "claim_id": claim.id,
                    "claim": claim.claim,
                    "subject": claim.subject,
                    "predicate": claim.predicate,
                    "object": claim.object,
                    "confidence": claim.confidence,
                    "citations": linked_citations,
                    # Extractor confidence is kept for compatibility; the evidence
                    # fields are what a reader should rank by, and they explain
                    # themselves through `components`.
                    "evidence_strength": (
                        round(score.strength, 4) if score else None
                    ),
                    "evidence_band": score.band if score else None,
                    "evidence_components": (
                        {k: round(v, 4) for k, v in score.components.items()}
                        if score
                        else None
                    ),
                    "independent_sources": (
                        score.provenance.independent_sources
                        if score and score.provenance
                        else None
                    ),
                }
            )

        # LLM Synthesis Prompt
        claims_text = "\n".join(
            [
                (
                    f"- {c.claim} "
                    f"(extractor: {c.confidence}; "
                    f"evidence: {evidence_by_id[c.id].band}"
                    f" from {evidence_by_id[c.id].provenance.independent_sources if evidence_by_id[c.id].provenance else 0}"
                    f" independent source(s))"
                )
                if c.id in evidence_by_id
                else f"- {c.claim} (extractor: {c.confidence})"
                for c in claims[:25]
            ]
        )
        prompt = f"""Target Research Question: "{session.question}"
Scope: {session.depth} depth, {session.geographic_scope} scope.

Extracted Factual Claims:
{claims_text or 'No claims extracted.'}

Total Sources Analyzed: {len(sources)}

Synthesize the final answer into structured JSON with:
- "executive_summary": string (2-3 sentences answering directly)
- "key_findings": array of strings (3 to 6 major thematic insights)
- "unknowns": array of strings (2 to 4 remaining open questions or data gaps)
"""

        # Rule-based fallback: still a usable report, but it leads with the
        # best-evidenced claims and says plainly that no model summarized them,
        # instead of presenting deterministic filler as synthesized analysis.
        high_confidence = [c for c in claims if c.confidence == "high"]
        exec_summary = (
            f"Collected {len(claims)} claim(s) from {len(sources)} source(s); "
            f"{evidence_stats['high']} scored high on evidence strength and "
            f"{evidence_stats['low']} scored low. "
            "No language model was available to summarize them, so the findings "
            "below are the extracted claims themselves."
        )
        # Lead with the best-evidenced claims rather than the ones the extractor
        # merely sounded surest about.
        best_claims = [
            score_claim_obj
            for _, score_claim_obj in sorted(
                ((evidence_by_id[c.id].strength, c) for c in claims if c.id in evidence_by_id),
                key=lambda pair: pair[0],
                reverse=True,
            )
        ] or high_confidence or claims
        key_findings = (
            [c.claim for c in best_claims[:5]]
            if best_claims
            else ["No definitive findings extracted."]
        )
        unknowns = [
            "Additional longitudinal data needed to confirm long-term outcomes."
        ]

        # Provenance of the executive summary: the rule-based fallback is still a
        # usable report, but consumers must be able to tell the two apart instead
        # of presenting deterministic filler as synthesized analysis.
        synthesis_mode = "fallback"

        try:
            raw_synthesis = await llm_router.generate(
                task=TaskType.REPORT,
                prompt=prompt,
                system_instruction=REPORT_SYNTHESIS_SYSTEM,
                temperature=0.2,
                session_id=self.session_id,
            )

            json_str = raw_synthesis.strip()
            match = re.search(r"\{.*\}", json_str, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                # Only a response that actually carried a summary counts as
                # synthesized; otherwise the badge would claim model quality for
                # text the fallback wrote.
                if parsed.get("executive_summary"):
                    exec_summary = parsed["executive_summary"]
                    key_findings = parsed.get("key_findings", key_findings)
                    unknowns = parsed.get("unknowns", unknowns)
                    synthesis_mode = "llm"
        except Exception as e:
            logger.warning(
                f"Error calling LLM for report synthesis: {e}. Falling back to rule-based summary."
            )

        # Build contradiction items
        contra_items = []
        for c in contradictions:
            contra_items.append(
                {
                    "id": c.id,
                    "claim_1": c.claim_1.claim if c.claim_1 else "",
                    "claim_2": c.claim_2.claim if c.claim_2 else "",
                    "severity": c.severity,
                    "explanation": c.resolution_note,
                }
            )

        # Versioned facts read as a timeline, not as disagreement; only groups whose
        # values actually conflict belong in the contradictions list.
        version_items = [
            group.to_dict()
            for group in version_groups
            if group.status in ("versioned", "conflicted")
        ]
        version_items.sort(
            key=lambda item: (
                item["status"] != "conflicted",
                item["span"].get("to") or 0,
            ),
            reverse=True,
        )

        final_report: dict[str, Any] = {
            "session_id": self.session_id,
            "question": session.question,
            "depth": session.depth,
            "executive_summary": exec_summary,
            "key_findings": key_findings,
            "evidence_table": evidence_items,
            "contradictions": contra_items,
            "versions": version_items,
            "unknowns": unknowns,
            "citations": citations,
            "metadata": {
                "total_sources": len(sources),
                "total_claims": len(claims),
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "evidence": evidence_stats,
                "versions": version_stats,
                "entity_merges": resolver.stats()["merges"],
                "coverage": compute_coverage_estimate(
                    claims_count=len(claims),
                    sources_count=len(sources),
                    min_sources_required=session.min_sources_required,
                    depth=session.depth,
                    nodes_count=len(nodes),
                ),
                "synthesis": synthesis_mode,
                "retry_count": retry_count,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        # Persist report to session
        await session_repo.save_report(
            self.session_id, final_report, mark_completed=mark_completed
        )
        logger.info(
            f"Final report successfully generated and saved for session {self.session_id}."
        )
        return final_report
