from __future__ import annotations

from .schema import SearchResult


def build_context(results: list[SearchResult], max_chars: int = 1800) -> dict:
    citations = []
    snippets = []
    seen = set()
    remaining = max_chars
    for result in results:
        chunk = result.chunk
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        snippet = chunk.text[:remaining]
        if not snippet:
            break
        snippets.append(f"[{chunk.chunk_id}] {snippet}")
        citations.append(
            {
                "chunk_id": chunk.chunk_id,
                "file_id": chunk.file_id,
                "name": chunk.source_name,
                "path": chunk.source_path,
                "version": chunk.source_version,
                "score": round(result.score, 4),
                "vector_score": round(result.vector_score, 4),
                "rerank_score": round(result.rerank_score, 4),
            }
        )
        remaining -= len(snippet)
        if remaining <= 0:
            break
    return {"context": "\n\n".join(snippets), "citations": citations}
