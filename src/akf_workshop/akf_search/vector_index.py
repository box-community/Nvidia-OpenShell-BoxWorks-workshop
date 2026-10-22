from __future__ import annotations

from dataclasses import replace

from .embed import embed_texts
from .index import ExactIndex
from .schema import KnowledgeChunk, SearchResult


class VectorIndex:
    """Chunk store that embeds chunks, computes the permission mask, and searches with `ExactIndex`."""

    def __init__(self) -> None:
        self.chunks: list[KnowledgeChunk] = []
        self.index = ExactIndex()

    def build(self, chunks: list[KnowledgeChunk]) -> None:
        vectors = embed_texts([chunk.text for chunk in chunks], input_type="passage")
        self.chunks = [replace(chunk, embedding=tuple(vector)) for chunk, vector in zip(chunks, vectors)]
        self.index.build([chunk.embedding for chunk in self.chunks])

    def search(
        self,
        query: str,
        user: str,
        groups: set[str],
        top_k: int = 6,
        candidate_k: int = 20,
    ) -> list[SearchResult]:
        if not self.chunks:
            return []
        allowed = [chunk.acl.allows(user, groups) for chunk in self.chunks]
        if not any(allowed):
            return []
        query_vector = tuple(embed_texts([query], input_type="query")[0])
        hits = self.index.search(query_vector, min(candidate_k, len(self.chunks)), allowed)
        return [SearchResult(chunk=self.chunks[row], vector_score=score) for row, score in hits][:top_k]
