"""Entity resolution — one node per real thing, not one per spelling.

The graph is only as good as its node identity. "OpenAI", "OpenAI Inc.",
"OpenAI, Inc." and "OpenAI company" are one organisation; leaving them as four
nodes splits its evidence four ways and then understates every claim about it.

Resolution is deliberately deterministic — normalisation first, then a *conservative*
similarity gate — because it runs over every claim of every iteration. It has to be
free, stable across runs, and testable offline. An LLM pass can refine it later, but
nothing in the graph may depend on one being available.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

# Corporate forms carry no identity: "Acme Ltd" and "Acme, Inc." are the same firm.
# Stored post-normalisation (lower-case, punctuation already stripped).
LEGAL_FORMS = frozenset(
    {
        "inc",
        "incorporated",
        "llc",
        "llp",
        "ltd",
        "limited",
        "corp",
        "corporation",
        "co",
        "company",
        "gmbh",
        "plc",
        "sa",
        "sas",
        "sarl",
        "ag",
        "bv",
        "nv",
        "ab",
        "as",
        "oy",
        "oyj",
        "pty",
        "pte",
        "srl",
        "spa",
        "kk",
        "holdings",
    }
)

LEADING_ARTICLES = frozenset({"the"})

# A fuzzy match at 0.90 is already very tight ("openai" vs "openai research" scores
# 0.55, so the two stay apart, which is correct — they are not the same node).
DEFAULT_SIMILARITY_THRESHOLD = 0.90

# Below this length, fuzzy matching does more harm than good: "AI" vs "A1" is not a
# resolution, it is a typo generator. Short labels must match exactly.
MIN_FUZZY_KEY_LENGTH = 4

# Characters worth keeping inside a name: '+' (C++), '/' (IoT/edge), '-' and '&'.
_PUNCTUATION = re.compile(r"[^\w\s&/\-+]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalize_entity(name: str) -> str:
    """Reduce a surface form to its identity-bearing key.

    Lower-cases, folds compatibility characters, drops punctuation and a trailing
    corporate form, and removes a leading article. "OpenAI, Inc." → "openai".
    """
    text = unicodedata.normalize("NFKC", name or "").strip().lower()
    text = text.replace("&", " and ")
    text = _PUNCTUATION.sub(" ", text)
    tokens = [token for token in _WHITESPACE.sub(" ", text).split(" ") if token]

    if tokens and tokens[0] in LEADING_ARTICLES:
        tokens = tokens[1:]
    while tokens and tokens[-1] in LEGAL_FORMS:
        tokens.pop()

    return " ".join(tokens)


def similarity(left: str, right: str) -> float:
    """Score how likely two *normalized* keys name the same thing (0..1).

    Character overlap is blended with token containment because containment is the
    stronger signal once legal forms are gone: "openai research" vs "openai" shares
    its only meaningful token, and that should count for more than the raw ratio.
    """
    if not left or not right:
        return 0.0

    ratio = SequenceMatcher(None, left, right).ratio()
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if left_tokens and right_tokens:
        containment = len(left_tokens & right_tokens) / min(
            len(left_tokens), len(right_tokens)
        )
        ratio = max(ratio, 0.6 * containment + 0.4 * ratio)
    return ratio


def should_merge(
    left_key: str, right_key: str, threshold: float = DEFAULT_SIMILARITY_THRESHOLD
) -> bool:
    """Decide whether two normalized keys are the same entity."""
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    if min(len(left_key), len(right_key)) < MIN_FUZZY_KEY_LENGTH:
        return False
    return similarity(left_key, right_key) >= threshold


@dataclass
class ResolvedEntity:
    """One canonical entity plus every surface form seen for it."""

    canonical: str
    aliases: set[str] = field(default_factory=set)
    entity_type: str = "entity"

    @property
    def alias_count(self) -> int:
        """How many *extra* spellings this canonical name absorbed."""
        return max(0, len(self.aliases) - 1)


class EntityResolver:
    """Maps every surface form in one run onto a canonical display name.

    ``seed()`` lets long-term memory preload aliases learned in earlier sessions, so
    a new run already knows that "Big Blue" is IBM without paying to discover it.

    Candidates are bucketed by first character: with hundreds of entities and
    thousands of claims, an all-pairs ``SequenceMatcher`` sweep is quadratic and this
    keeps resolution linear in practice. Two names that do not share a first
    character are not merged, deliberately — the acronym cases that would need it
    ("IBM" vs "International Business Machines") come from the alias table instead.
    """

    def __init__(self, threshold: float = DEFAULT_SIMILARITY_THRESHOLD) -> None:
        self._threshold = threshold
        self._entities: dict[str, ResolvedEntity] = {}
        # normalized alias key -> normalized canonical key
        self._alias_index: dict[str, str] = {}
        self._buckets: dict[str, set[str]] = {}
        #: Fuzzy (similarity-gated) merges — the risky kind, worth watching.
        self.merges = 0
        #: Every surface form folded into an already-known entity, exact or fuzzy.
        self.aliases_absorbed = 0

    # ─── seeding ─────────────────────────────────────────────────────────────
    def seed(self, aliases: dict[str, list[str]]) -> None:
        """Preload canonical → aliases mappings (e.g. from long-term memory)."""
        for canonical, surfaces in aliases.items():
            entity = self._register(canonical, entity_type="seeded")
            for surface in surfaces:
                key = normalize_entity(surface)
                if key:
                    entity.aliases.add(surface.strip())
                    self._alias_index[key] = normalize_entity(canonical)

    def _register(self, name: str, entity_type: str = "entity") -> ResolvedEntity:
        key = normalize_entity(name)
        entity = self._entities.get(key)
        if entity is None:
            entity = ResolvedEntity(
                canonical=(name or "").strip(), entity_type=entity_type
            )
            self._entities[key] = entity
            self._buckets.setdefault(key[:1], set()).add(key)
        return entity

    # ─── resolution ──────────────────────────────────────────────────────────
    def resolve(self, name: str, entity_type: str = "entity") -> str:
        """Return the canonical display name for a surface form."""
        display = (name or "").strip()
        key = normalize_entity(display)
        if not key:
            return display

        known = self._alias_index.get(key)
        if known is not None and known in self._entities:
            entity = self._entities[known]
            if display and display not in entity.aliases:
                entity.aliases.add(display)
                self.aliases_absorbed += 1
            return entity.canonical

        best_key: str | None = None
        best_score = 0.0
        for candidate_key in self._buckets.get(key[:1], ()):
            score = similarity(key, candidate_key)
            if score > best_score:
                best_key, best_score = candidate_key, score

        if (
            best_key is not None
            and should_merge(key, best_key, self._threshold)
            and best_key in self._entities
        ):
            entity = self._entities[best_key]
            entity.aliases.add(display)
            self._alias_index[key] = best_key
            self.merges += 1
            self.aliases_absorbed += 1
            return entity.canonical

        # New entity: the first spelling seen wins, so the graph is stable and the
        # label never changes under the reader between iterations.
        entity = self._register(display, entity_type=entity_type)
        entity.aliases.add(display)
        self._alias_index[key] = key
        return entity.canonical

    def canonical_of(self, name: str) -> str:
        """Return the canonical *key* (normalized) for a surface form."""
        return self._alias_index.get(normalize_entity(name), normalize_entity(name))

    def aliases_for(self, canonical: str) -> list[str]:
        """Every surface form absorbed by a canonical name, sorted for stability."""
        entity = self._entities.get(normalize_entity(canonical))
        return sorted(entity.aliases) if entity else []

    def entities(self) -> list[ResolvedEntity]:
        """All canonical entities, in first-seen order."""
        return list(self._entities.values())

    def alias_table(self) -> dict[str, list[str]]:
        """Canonical display name → aliases, for persistence into long-term memory."""
        return {
            entity.canonical: sorted(entity.aliases)
            for entity in self._entities.values()
            if entity.alias_count > 0
        }

    def stats(self) -> dict[str, int]:
        """Resolution counters for telemetry and tests."""
        return {
            "entities": len(self._entities),
            "aliases": sum(len(e.aliases) for e in self._entities.values()),
            "merges": self.merges,
            "aliases_absorbed": self.aliases_absorbed,
        }
