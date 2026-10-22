from __future__ import annotations

import time
from dataclasses import dataclass

from akf_workshop.akf_search.pipeline import SearchPipeline


@dataclass
class RetrievalSkill:
    pipeline: SearchPipeline

    def __call__(self, query: str, user: str, groups: set[str]) -> dict:
        start = time.perf_counter()
        retrieved = self.pipeline.retrieve(query=query, user=user, groups=groups)
        citations = retrieved["citations"]
        best_score = citations[0]["score"] if citations else 0.0
        best_rerank = retrieved["results"][0].rerank_score if retrieved["results"] else 0.0
        status = retrieved.get("status") or ("ok" if citations and best_score >= 0.3 and best_rerank >= 0.75 else "insufficient_context")
        return {
            "skill": "retrieval",
            "status": status,
            "answer": _extract_answer(query, retrieved["context"]) if status == "ok" else "I could not find enough permitted Box context to answer.",
            "evidence": citations,
            "context": retrieved["context"],
            "trace_ms": round((time.perf_counter() - start) * 1000, 2),
            "production_swap": "Use Nemotron Parse, Nemotron Embed, and Nemotron Rerank.",
        }


def _extract_answer(query: str, context: str) -> str:
    first_line = next((line for line in context.splitlines() if line.strip() and not line.startswith("[")), "")
    if not first_line:
        first_line = context.splitlines()[0] if context else ""
    return f"Based on permitted Box context, {first_line[:320]}"
