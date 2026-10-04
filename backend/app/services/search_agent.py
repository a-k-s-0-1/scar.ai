"""Search Agent executing queries, deduplicating sources, and computing domain credibility."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import RateLimitExceededError
from app.database.models import Source
from app.database.repository import SourceRepository
from app.integrations.tavily_client import TavilyClient
from app.utils.helpers import compute_content_hash, compute_url_domain
from app.utils.logger import logger
from app.utils.parsers import clean_html_content

HIGH_AUTHORITY_DOMAINS = {
    "arxiv.org": 0.95,
    "nature.com": 0.95,
    "science.org": 0.95,
    "nih.gov": 0.95,
    "ncbi.nlm.nih.gov": 0.95,
    "ieee.org": 0.92,
    "acm.org": 0.92,
    "reuters.com": 0.85,
    "bloomberg.com": 0.85,
    "bbc.com": 0.82,
    "bbc.co.uk": 0.82,
    "wikipedia.org": 0.75,
}

LOW_AUTHORITY_DOMAINS = {
    "reddit.com": 0.35,
    "twitter.com": 0.30,
    "x.com": 0.30,
    "quora.com": 0.40,
    "medium.com": 0.50,
}


def estimate_source_credibility(url: str) -> float:
    """Calculate baseline credibility score (0.0 to 1.0) based on domain authority."""
    domain = compute_url_domain(url)

    # Check exact domain matches
    for auth_domain, score in HIGH_AUTHORITY_DOMAINS.items():
        if domain == auth_domain or domain.endswith("." + auth_domain):
            return score

    for low_domain, score in LOW_AUTHORITY_DOMAINS.items():
        if domain == low_domain or domain.endswith("." + low_domain):
            return score

    # TLD heuristics
    if domain.endswith(".edu") or domain.endswith(".gov") or domain.endswith(".mil"):
        return 0.90
    if domain.endswith(".org"):
        return 0.70

    return 0.60


class SearchAgent:
    """Agent executing web searches, deduplicating results, and persisting sources."""

    def __init__(self, session_id: str, max_queries: int = 50) -> None:
        self.session_id = session_id
        self.max_queries = max_queries
        self.queries_executed = 0
        self.client = TavilyClient()

    async def search(
        self, query: str, db: AsyncSession, max_results: int = 10
    ) -> list[Source]:
        """Execute a web search, filter duplicates, and save new sources to database."""
        if self.queries_executed >= self.max_queries:
            raise RateLimitExceededError("Search Queries per Session", retry_after=300)

        self.queries_executed += 1
        logger.info(
            f"Session {self.session_id} executing search ({self.queries_executed}/{self.max_queries}): '{query}'"
        )

        raw_results = await self.client.search(query=query, max_results=max_results)

        source_repo = SourceRepository(db)
        existing_urls = await source_repo.get_existing_urls(self.session_id)

        new_sources: list[Source] = []

        for item in raw_results:
            url = item["url"]
            if url in existing_urls:
                continue

            content = item.get("content", "")
            cleaned_text = clean_html_content(content)
            content_hash = compute_content_hash(cleaned_text) if cleaned_text else None
            credibility = estimate_source_credibility(url)

            # Determine published_at
            pub_date: datetime | None = None
            if item.get("published_date"):
                try:
                    pub_date = datetime.fromisoformat(
                        item["published_date"].replace("Z", "+00:00")
                    )
                except Exception:
                    pub_date = None

            source = await source_repo.create(
                session_id=self.session_id,
                url=url,
                title=item.get("title") or url,
                content=cleaned_text,
                source_type="webpage",
                credibility_score=credibility,
                published_at=pub_date,
                content_hash=content_hash,
            )
            existing_urls.add(url)
            new_sources.append(source)

        logger.info(
            f"Search found {len(raw_results)} results, saved {len(new_sources)} new unique sources."
        )
        return new_sources
