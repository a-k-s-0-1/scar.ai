"""Contradiction detector and research gap identifier using Tier 3 reasoning."""

import json
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Claim, Contradiction
from app.database.repository import ClaimRepository, ContradictionRepository
from app.integrations.llm_router import TaskType, llm_router
from app.utils.logger import logger

CONTRADICTION_VERIFICATION_PROMPT = """Analyze the following pair of claims extracted during a research session.
Determine if they genuinely contradict each other, present conflicting empirical data, or describe mutually incompatible outcomes.

Claim A: "{claim_a}"
Claim B: "{claim_b}"

If they DO contradict:
- severity: "high" (direct factual or quantitative impossibility), "medium" (differing estimates or timelines), or "low" (nuanced disagreement in terminology)
- explanation: A concise 1-2 sentence explanation of the conflict.

Return ONLY a JSON object:
{{
  "contradicts": true,
  "severity": "medium",
  "explanation": "..."
}}
If they do NOT contradict, return:
{{
  "contradicts": false
}}
"""


class ContradictionDetector:
    """Identifies conflicting claims and computes knowledge coverage and gap areas."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

    async def detect_contradictions(
        self,
        db: AsyncSession,
        max_comparisons: int = 15,
    ) -> list[Contradiction]:
        """Examine claims in session to detect conflicting assertions."""
        claim_repo = ClaimRepository(db)
        contra_repo = ContradictionRepository(db)
        claims = await claim_repo.get_by_session(self.session_id)

        if len(claims) < 2:
            return []

        # Find candidate pairs (share subject or keywords)
        candidate_pairs: list[tuple[Claim, Claim]] = []
        for i in range(len(claims)):
            for j in range(i + 1, len(claims)):
                c1, c2 = claims[i], claims[j]
                # Compare if subjects overlap or if claims are reasonably distinct
                if (
                    c1.subject
                    and c2.subject
                    and c1.subject.lower() == c2.subject.lower()
                    or c1.predicate
                    and c2.predicate
                    and c1.predicate.lower() == c2.predicate.lower()
                ):
                    candidate_pairs.append((c1, c2))

        # If not enough structural overlaps, check top recent pairs
        if not candidate_pairs:
            candidate_pairs = [
                (claims[i], claims[j])
                for i in range(min(5, len(claims)))
                for j in range(i + 1, min(6, len(claims)))
            ]

        candidate_pairs = candidate_pairs[:max_comparisons]
        detected: list[Contradiction] = []

        # Pairs already recorded as contradictions were verified in an earlier
        # iteration; re-running the LLM on them burns free-tier quota for a
        # foregone conclusion (the repository would reject the duplicate anyway).
        already_judged = {
            frozenset((c.claim_1_id, c.claim_2_id))
            for c in await contra_repo.get_by_session(self.session_id)
        }

        for c1, c2 in candidate_pairs:
            if frozenset((c1.id, c2.id)) in already_judged:
                continue

            prompt = CONTRADICTION_VERIFICATION_PROMPT.format(
                claim_a=c1.claim,
                claim_b=c2.claim,
            )

            try:
                response = await llm_router.generate(
                    task=TaskType.CONTRADICTION,
                    prompt=prompt,
                    temperature=0.1,
                    session_id=self.session_id,
                )

                json_str = response.strip()
                match = re.search(r"\{.*\}", json_str, re.DOTALL)
                if match:
                    json_str = match.group(0)

                result = json.loads(json_str)
                if result.get("contradicts") is True:
                    severity = result.get("severity", "medium").lower()
                    if severity not in ("high", "medium", "low"):
                        severity = "medium"
                    explanation = result.get("explanation", "Conflicting assertions.")

                    contradiction = await contra_repo.create(
                        session_id=self.session_id,
                        claim_1_id=c1.id,
                        claim_2_id=c2.id,
                        severity=severity,
                        resolution_note=explanation,
                    )
                    detected.append(contradiction)
                    logger.info(
                        f"Detected contradiction between claim {c1.id} and {c2.id}: {explanation}"
                    )
            except Exception as e:
                logger.warning(f"Error evaluating contradiction candidate pair: {e}")

        return detected

    async def identify_knowledge_gaps(
        self,
        db: AsyncSession,
        question: str,
    ) -> list[str]:
        """Identify sub-questions or missing facets of the user question that need deeper search."""
        claim_repo = ClaimRepository(db)
        claims = await claim_repo.get_by_session(self.session_id)

        claims_summary = "\n".join([f"- {c.claim}" for c in claims[:15]])

        prompt = f"""Target Research Question: "{question}"

Current Established Claims:
{claims_summary or "None yet."}

Identify 1 to 3 specific sub-topics, missing empirical details, or follow-up search queries required to complete a thorough investigation.
Output format: A JSON array of string search queries only.
Example: ["solid-state battery degradation temperature limits", "commercial solid-state EV release dates"]
"""
        try:
            res = await llm_router.generate(
                task=TaskType.REASON,
                prompt=prompt,
                temperature=0.2,
                session_id=self.session_id,
            )
            json_str = res.strip()
            match = re.search(r"\[.*\]", json_str, re.DOTALL)
            if match:
                queries = json.loads(match.group(0))
                if isinstance(queries, list):
                    return [str(q).strip() for q in queries if str(q).strip()]
        except Exception as e:
            logger.warning(f"Failed to identify knowledge gaps: {e}")

        return []
