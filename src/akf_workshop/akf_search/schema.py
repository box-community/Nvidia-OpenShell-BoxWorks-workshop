from __future__ import annotations

from dataclasses import dataclass

from akf_workshop.box_source.schema import AccessControl


@dataclass(frozen=True)
class ParsedSection:
    file_id: str
    heading: str
    text: str
    source_name: str
    source_path: str
    source_version: str
    labels: tuple[str, ...]
    acl: AccessControl
    kind: str = "text"  # text | table | notice


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    file_id: str
    text: str
    source_name: str
    source_path: str
    source_version: str
    labels: tuple[str, ...]
    acl: AccessControl
    embedding: tuple[float, ...] = ()


@dataclass(frozen=True)
class SearchResult:
    chunk: KnowledgeChunk
    vector_score: float
    rerank_score: float = 0.0
    rerank_source: str = "lexical"

    @property
    def score(self) -> float:
        return self.vector_score + self.rerank_score
