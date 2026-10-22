from __future__ import annotations

import os
import unittest
import urllib.error
from unittest.mock import patch

from akf_workshop.akf_search import rerank as rerank_mod
from akf_workshop.akf_search.schema import KnowledgeChunk, SearchResult
from akf_workshop.box_source.schema import AccessControl

TEXTS = [
    "The catalog lists HX-4410 with a two-year warranty.",
    "Enterprise incidents with customer impact should be escalated to the support lead within 30 minutes.",
    "Chunk size should be treated as a quality and cost knob.",
]


def _result(i: int, text: str, vector_score: float) -> SearchResult:
    chunk = KnowledgeChunk(
        chunk_id=f"box-test:{i:04d}", file_id="box-test", text=text, source_name="x.md", source_path="/x.md",
        source_version="v1", labels=(), acl=AccessControl(groups=("workshop-attendees",)),
    )
    return SearchResult(chunk=chunk, vector_score=vector_score)


RESULTS = [_result(0, TEXTS[0], 0.3), _result(1, TEXTS[1], 0.5), _result(2, TEXTS[2], 0.2)]


class RerankDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        patch.dict(os.environ, {"NVIDIA_USE_REMOTE": "0"}).start()
        self.addCleanup(patch.stopall)

    def test_offline_path_is_unchanged(self) -> None:
        out = rerank_mod.rerank("escalated", RESULTS, top_k=2)
        self.assertEqual(out[0].rerank_source, "lexical")
        self.assertEqual(out, rerank_mod.rerank_lexical("escalated", RESULTS, top_k=2))

    def test_hosted_path_orders_by_logit(self) -> None:
        with patch.object(rerank_mod, "remote_enabled", lambda: True), \
             patch.object(rerank_mod, "rerank_remote", lambda q, p: [(1, 5.14), (2, -7.98), (0, -9.09)]):
            out = rerank_mod.rerank("q", RESULTS, top_k=3)
        self.assertEqual([r.chunk.chunk_id for r in out],
                         [RESULTS[1].chunk.chunk_id, RESULTS[2].chunk.chunk_id, RESULTS[0].chunk.chunk_id])
        self.assertAlmostEqual(out[0].rerank_score, 5.14)
        self.assertEqual(out[0].rerank_source, "hosted")

    def test_hosted_failure_falls_back_to_lexical(self) -> None:
        def boom(q, p):
            raise RuntimeError("NVIDIA API error 429: rate limited")
        with patch.object(rerank_mod, "remote_enabled", lambda: True), patch.object(rerank_mod, "rerank_remote", boom):
            out = rerank_mod.rerank("escalated", RESULTS, top_k=2)
        self.assertEqual(out[0].rerank_source, "lexical-fallback")

    def test_network_error_falls_back_to_lexical(self) -> None:
        def boom(q, p):
            raise urllib.error.URLError("dns")
        with patch.object(rerank_mod, "remote_enabled", lambda: True), patch.object(rerank_mod, "rerank_remote", boom):
            self.assertEqual(rerank_mod.rerank("escalated", RESULTS, top_k=2)[0].rerank_source, "lexical-fallback")

    def test_empty_results_make_no_call(self) -> None:
        def boom(q, p):
            raise AssertionError("must not be called")
        with patch.object(rerank_mod, "remote_enabled", lambda: True), patch.object(rerank_mod, "rerank_remote", boom):
            self.assertEqual(rerank_mod.rerank("q", [], top_k=4), [])


if __name__ == "__main__":
    unittest.main()
