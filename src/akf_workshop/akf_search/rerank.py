from __future__ import annotations

import re
from dataclasses import replace

from akf_workshop.nvidia_clients import remote_enabled, rerank_remote

from .schema import SearchResult


TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "for",
    "how",
    "in",
    "is",
    "of",
    "or",
    "should",
    "the",
    "to",
    "when",
    "with",
}


def rerank(query: str, results: list[SearchResult], top_k: int = 4) -> list[SearchResult]:
    """Order candidates with the hosted Nemotron reranker when remote mode is on, else lexically.

    Hosted: rerank_score is the model logit and the order follows it. Any failure of the hosted
    call falls back to the lexical reranker and marks results "lexical-fallback".
    """
    if not results:
        return []
    if not remote_enabled():
        return rerank_lexical(query, results, top_k)
    try:
        pairs = rerank_remote(query, [result.chunk.text for result in results])
    except (RuntimeError, ValueError, OSError):
        return [replace(result, rerank_source="lexical-fallback") for result in rerank_lexical(query, results, top_k)]
    rescored = [replace(results[index], rerank_score=logit, rerank_source="hosted") for index, logit in pairs]
    return rescored[:top_k]


def rerank_lexical(query: str, results: list[SearchResult], top_k: int = 4) -> list[SearchResult]:
    query_terms = _terms(query)
    rescored = []
    for result in results:
        chunk_terms = _terms(result.chunk.text)
        overlap = len(query_terms.intersection(chunk_terms))
        coverage = overlap / max(len(query_terms), 1)
        rescored.append(replace(result, rerank_score=coverage * 2.0, rerank_source="lexical"))
    return sorted(rescored, key=lambda result: result.score, reverse=True)[:top_k]


def _terms(text: str) -> set[str]:
    return {token for token in TOKEN_RE.findall(text.lower()) if token not in STOPWORDS}
