"""Claim Extractor parsing factual claims from source texts using Tier 2 LLM routing."""

import json
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Claim, Source
from app.database.repository import ClaimRepository
from app.integrations.llm_router import TaskType, llm_router
from app.utils.logger import logger
from app.utils.parsers import truncate_for_llm

EXTRACTION_SYSTEM_PROMPT = """You are an expert factual research analyst.
Your job is to extract atomic, factual claims from the provided source texts.
Strict requirements:
1. Each claim must be an objective factual proposition, not an opinion or promotional text.
2. Provide structured components: subject, predicate, object.
3. Assign confidence based on the rigor of the source and certainty of language:
   - "high": established empirical data, peer-reviewed findings, official government reports
   - "medium": credible news reports, company announcements, preliminary studies
   - "low": speculative statements, unverified rumors, single source claims
4. Output MUST be valid JSON only. No conversational intro or markdown backticks.

Example JSON structure:
{
  "claims": [
    {
      "claim": "Quantum dots improve display color gamut by 30% over conventional LCDs.",
      "subject": "Quantum dots",
      "predicate": "improve",
      "object": "display color gamut by 30%",
      "confidence": "high"
    }
  ]
}
"""


class ClaimExtractor:
    """Extracts factual claims and links them to source documents."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

    async def extract_from_sources(
        self,
        sources: list[Source],
        question: str,
        db: AsyncSession,
    ) -> list[Claim]:
        """Extract atomic claims from a batch of sources and persist them to DB."""
        if not sources:
            return []

        claim_repo = ClaimRepository(db)
        new_claims: list[Claim] = []

        for source in sources:
            if not source.content or len(source.content.strip()) < 50:
                continue

            truncated_content = truncate_for_llm(source.content, max_chars=4000)
            prompt = f"""Research Question: {question}

Source Document:
Title: {source.title or 'Unknown'}
URL: {source.url}
Content:
{truncated_content}

Extract between 2 and 6 key atomic factual claims directly relevant to answering the research question.
Return ONLY valid JSON matching the specified schema.
"""

            raw_response = ""
            parsed_data: dict[str, Any] | None = None

            for attempt in range(3):
                try:
                    raw_response = await llm_router.generate(
                        task=TaskType.EXTRACT,
                        prompt=prompt,
                        system_instruction=EXTRACTION_SYSTEM_PROMPT,
                        temperature=0.1,
                        session_id=self.session_id,
                    )

                    # Extract JSON from potential markdown wrapping
                    json_str = raw_response.strip()
                    if "```json" in json_str:
                        json_str = (
                            json_str.split("```json", 1)[1].split("```", 1)[0].strip()
                        )
                    elif "```" in json_str:
                        json_str = (
                            json_str.split("```", 1)[1].split("```", 1)[0].strip()
                        )

                    match = re.search(r"\{.*\}", json_str, re.DOTALL)
                    if match:
                        json_str = match.group(0)

                    parsed_data = json.loads(json_str)
                    break
                except Exception as e:
                    logger.warning(
                        f"Claim extraction JSON parse error (attempt {attempt + 1}/3): {e}"
                    )

            if not parsed_data or "claims" not in parsed_data:
                logger.warning(
                    f"Failed to extract structured claims from source: {source.url}"
                )
                continue

            for item in parsed_data.get("claims", []):
                claim_text = item.get("claim", "").strip()
                if not claim_text or len(claim_text) < 10:
                    continue

                subject = (item.get("subject") or "").strip()[:255] or None
                predicate = (item.get("predicate") or "").strip()[:255] or None
                obj = (item.get("object") or "").strip() or None
                confidence = item.get("confidence", "medium").lower()
                if confidence not in ("high", "medium", "low"):
                    confidence = "medium"

                # Persist claim
                created_claim = await claim_repo.create(
                    session_id=self.session_id,
                    claim_text=claim_text,
                    subject=subject,
                    predicate=predicate,
                    obj=obj,
                    confidence=confidence,
                )

                # Link claim to source
                await claim_repo.link_source(
                    claim_id=created_claim.id,
                    source_id=source.id,
                    support_type="supports",
                    confidence=source.credibility_score,
                )

                new_claims.append(created_claim)

        logger.info(
            f"Extracted and saved {len(new_claims)} claims across {len(sources)} sources."
        )
        return new_claims
