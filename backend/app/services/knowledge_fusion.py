"""Iterative Knowledge Fusion (IKF) layer constructing the entity-relationship knowledge graph.

IKF 2.0 changes three things here, all of them about the same problem — a graph that
looks denser than the evidence behind it:

* entities are resolved to a canonical name, so "OpenAI Inc." lands on the "OpenAI"
  node instead of splitting its evidence across a second one;
* edge strength comes from *evidence strength* when the caller has scored the claims,
  replacing a fixed 0.9/0.7/0.5 guess based on how confident the extractor sounded;
* every edge records provenance — which sources and claims produced it, how many of
  those sources are independent, and when it was extracted.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Claim, KnowledgeNode
from app.database.repository import ClaimRepository, KnowledgeRepository
from app.services.ikf.entity_resolution import EntityResolver
from app.services.ikf.evidence import EvidenceScore
from app.services.ikf.provenance import edge_provenance
from app.services.ikf.service import source_refs_from_links
from app.utils.logger import logger

# Fallback edge strength when no evidence score was supplied by the caller.
CONFIDENCE_FALLBACK_STRENGTH = {"high": 0.9, "medium": 0.7, "low": 0.5}
DEFAULT_FALLBACK_STRENGTH = 0.6


class KnowledgeFusion:
    """Iterative Knowledge Fusion: transforms extracted claims into an interconnected knowledge graph."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

    async def fuse_claims(
        self,
        claims: list[Claim],
        db: AsyncSession,
        resolver: EntityResolver | None = None,
        evidence: dict[str, EvidenceScore] | None = None,
    ) -> tuple[int, int]:
        """Process claims to create or update knowledge graph nodes and relational edges.

        ``resolver`` should be the session-scoped ``EntityResolver`` so aliases learned
        in earlier iterations keep working; passing none keeps the pre-2.0 behaviour of
        matching on the raw string. ``evidence`` maps claim id → score and, when given,
        decides both the edge strength and the recorded provenance.

        Returns:
            (new_nodes_count, new_edges_count)
        """
        if not claims:
            return 0, 0

        repo = KnowledgeRepository(db)
        resolver = resolver or EntityResolver()
        # Loaded in one query rather than off the instances: the research loop passes
        # claims whose session has already closed, where a lazy load would raise.
        links_by_claim = await ClaimRepository(db).get_links_for_claims(
            [claim.id for claim in claims]
        )
        initial_nodes, initial_edges = await repo.get_graph(self.session_id)
        node_map: dict[str, KnowledgeNode] = {
            n.entity.lower(): n for n in initial_nodes
        }
        edge_set: set[tuple[str, str, str]] = {
            (e.source_node_id, e.target_node_id, (e.relationship_type or "").lower())
            for e in initial_edges
        }

        created_nodes = 0
        created_edges = 0

        for claim in claims:
            # Resolution is what collapses "OpenAI Inc." onto "OpenAI"; the display
            # label stays the first spelling seen so the graph does not relabel itself
            # mid-run.
            subject_str = resolver.resolve((claim.subject or "").strip())
            predicate_str = (claim.predicate or "relates_to").strip()
            object_str = resolver.resolve((claim.object or "").strip())

            # Filter trivial or excessively long strings as nodes
            if not subject_str or len(subject_str) < 2 or len(subject_str) > 80:
                continue

            # Subject Node
            subj_key = subject_str.lower()
            if subj_key not in node_map:
                subj_node = await repo.get_or_create_node(
                    session_id=self.session_id,
                    entity=subject_str,
                    entity_type="entity",
                )
                node_map[subj_key] = subj_node
                created_nodes += 1
            else:
                subj_node = node_map[subj_key]

            # If object is also a succinct entity, create an edge
            if object_str and 2 <= len(object_str) <= 80:
                obj_key = object_str.lower()
                if obj_key not in node_map:
                    obj_node = await repo.get_or_create_node(
                        session_id=self.session_id,
                        entity=object_str,
                        entity_type="concept",
                    )
                    node_map[obj_key] = obj_node
                    created_nodes += 1
                else:
                    obj_node = node_map[obj_key]

                # Create or find the edge, then record this claim's evidence against it.
                edge_tuple = (subj_node.id, obj_node.id, predicate_str.lower())
                score = (evidence or {}).get(claim.id)
                strength = (
                    score.strength
                    if score is not None
                    else CONFIDENCE_FALLBACK_STRENGTH.get(
                        (claim.confidence or "").lower(),
                        DEFAULT_FALLBACK_STRENGTH,
                    )
                )
                edge = await repo.add_edge(
                    session_id=self.session_id,
                    source_node_id=subj_node.id,
                    target_node_id=obj_node.id,
                    relationship_type=predicate_str,
                    strength=strength,
                )
                if edge_tuple not in edge_set:
                    edge_set.add(edge_tuple)
                    created_edges += 1
                elif score is not None and strength > edge.strength:
                    # A later restatement that is better evidenced upgrades the edge;
                    # the reverse never downgrades it.
                    edge.strength = strength

                # Recorded for *every* supporting claim, not just the one that happened
                # to create the edge: the second assertion is the entire point of
                # evidence aggregation, and provenance merges rather than overwrites.
                await self._record_provenance(
                    repo, edge.id, claim, links_by_claim.get(claim.id, [])
                )

        logger.info(
            f"Knowledge fusion complete for session {self.session_id}: "
            f"+{created_nodes} nodes, +{created_edges} edges "
            f"({resolver.stats()['merges']} entity merges)."
        )
        return created_nodes, created_edges

    async def _record_provenance(
        self,
        repo: KnowledgeRepository,
        edge_id: str,
        claim: Claim,
        links: list[object],
    ) -> None:
        """Attach the claim's sources to its edge.

        Skipped for an unsourced claim: writing an empty provenance record would make
        an unevidenced edge look *recorded* rather than unsupported.
        """
        refs = source_refs_from_links(links)
        if not refs:
            return
        payload = edge_provenance(refs, [claim.id], extracted_at=claim.created_at)
        await repo.upsert_edge_provenance(self.session_id, edge_id, payload)
