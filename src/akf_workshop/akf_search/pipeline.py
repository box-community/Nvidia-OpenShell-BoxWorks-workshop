from __future__ import annotations

import os
from pathlib import Path

from akf_workshop.box_source.source import make_adapter

from .chunk import chunk_sections
from .context import build_context
from .vector_index import VectorIndex
from .parse import parse_artifact
from .rerank import rerank


class SearchPipeline:
    def __init__(self, sample_box_root: Path):
        self.sample_box_root = Path(sample_box_root)
        self.adapter = make_adapter(self.sample_box_root)
        self.index = VectorIndex()

    def ingest(self) -> dict:
        sections = []
        for listed_file in self.adapter.list_files():
            file_with_content = self.adapter.get_file(listed_file.file_id)
            sections.extend(parse_artifact(file_with_content, local_root=self.sample_box_root))
        chunks = chunk_sections(sections, max_words=int(os.getenv("AKF_CHUNK_WORDS", "120")))
        self.index.build(chunks)
        notices = [section.text for section in sections if section.kind == "notice"]
        return {"files": len(self.adapter.list_files()), "sections": len(sections), "chunks": len(chunks), "notices": notices}

    def retrieve(self, query: str, user: str, groups: set[str], top_k: int = 4) -> dict:
        vector_results = self.index.search(query, user=user, groups=groups, top_k=12)
        reranked = rerank(query, vector_results, top_k=top_k)
        context = build_context(reranked)
        context["results"] = reranked
        context.update(_status_fields(reranked, context["citations"]))
        return context


def _status_fields(reranked: list, citations: list[dict]) -> dict:
    """Decide ok vs insufficient_context inside the lane.

    Hosted rerank (nemotron-3.5-rerank-8b): the top logit must clear AKF_RERANK_MIN_LOGIT (default -3.1).
    Measured on the golden questions: answerable ones scored -2.87 and up, no-answer ones -3.31 and below.
    The threshold depends on the model and the content; recalibrate it when either changes.
    Lexical rerank (offline or fallback): the starter's original rule.
    """
    if not reranked:
        return {"status": "insufficient_context", "rerank_source": "none", "top_rerank_score": None, "rerank_gap": None}
    top = reranked[0]
    gap = top.rerank_score - reranked[1].rerank_score if len(reranked) > 1 else None
    if top.rerank_source == "hosted":
        threshold = float(os.getenv("AKF_RERANK_MIN_LOGIT", "-3.1"))
        ok = top.rerank_score >= threshold
    else:
        ok = bool(citations) and citations[0]["score"] >= 0.3 and top.rerank_score >= 0.75
    return {
        "status": "ok" if ok else "insufficient_context",
        "rerank_source": top.rerank_source,
        "top_rerank_score": top.rerank_score,
        "rerank_gap": gap,
    }
