"""Minimal retrieval boundary for deterministic filter-then-rank flows."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VectorIndexDocument:
    id: str
    content: str


@dataclass(frozen=True, slots=True)
class VectorIndexMatch:
    document_id: str
    score: float


class VectorIndex(ABC):
    @abstractmethod
    async def rank(
        self,
        *,
        query: str,
        candidates: Sequence[VectorIndexDocument],
        limit: int = 10,
    ) -> list[VectorIndexMatch]: ...


class InMemoryVectorIndex(VectorIndex):
    async def rank(
        self,
        *,
        query: str,
        candidates: Sequence[VectorIndexDocument],
        limit: int = 10,
    ) -> list[VectorIndexMatch]:
        if limit <= 0:
            return []

        query_terms = [term for term in query.casefold().split() if term]
        scored_matches: list[VectorIndexMatch] = []

        for candidate in candidates:
            candidate_text = candidate.content.casefold()
            score = sum(
                float(len(query_terms) - index)
                for index, term in enumerate(query_terms)
                if term in candidate_text
            )
            if score <= 0:
                continue
            scored_matches.append(VectorIndexMatch(document_id=candidate.id, score=score))

        scored_matches.sort(key=lambda match: match.score, reverse=True)
        return scored_matches[:limit]
