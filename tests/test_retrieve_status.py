from __future__ import annotations

import os as _os

_os.environ.pop("BOX_FOLDER_ID", None)  # these tests use the local sample_box, never live Box

import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from akf_workshop.akf_search import rerank as rerank_mod
from akf_workshop.akf_search.pipeline import SearchPipeline

SAMPLE = Path(__file__).resolve().parents[1] / "sample_box"
LEAD, LEAD_GROUPS = "support-lead@example.com", {"support-leads"}
DEV, DEV_GROUPS = "dev@example.com", {"workshop-attendees"}


@contextmanager
def hosted_rerank(pairs):
    """Pretend remote mode is on and the hosted reranker returned `pairs`, padded with (i, -99.0)
    for every candidate index not in `pairs`, so the one-pair-per-passage contract holds."""
    given = dict(pairs)

    def fake(query, passages):
        full = [(i, given.get(i, -99.0)) for i in range(len(passages))]
        return sorted(full, key=lambda pair: pair[1], reverse=True)

    with patch.object(rerank_mod, "remote_enabled", lambda: True), patch.object(rerank_mod, "rerank_remote", fake):
        yield


class RetrieveStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        patch.dict(os.environ, {"NVIDIA_USE_REMOTE": "0"}).start()
        self.addCleanup(patch.stopall)
        self.pipe = SearchPipeline(SAMPLE)
        self.pipe.ingest()

    def test_hosted_status_ok_above_threshold(self) -> None:
        with hosted_rerank([(0, 2.0), (1, -1.0)]):
            out = self.pipe.retrieve("When should enterprise incidents be escalated?", user=LEAD, groups=LEAD_GROUPS)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["rerank_source"], "hosted")
        self.assertAlmostEqual(out["top_rerank_score"], 2.0)
        self.assertAlmostEqual(out["rerank_gap"], 3.0)
        self.assertIn("rerank_score", out["citations"][0])
        self.assertIn("vector_score", out["citations"][0])

    def test_hosted_status_insufficient_below_threshold(self) -> None:
        with hosted_rerank([(0, -8.4), (1, -9.0)]):
            out = self.pipe.retrieve("HX-9000 warranty", user=LEAD, groups=LEAD_GROUPS)
        self.assertEqual(out["status"], "insufficient_context")

    def test_default_threshold_is_minus_three_point_one(self) -> None:
        with hosted_rerank([(0, -3.0)]):
            self.assertEqual(self.pipe.retrieve("q", user=LEAD, groups=LEAD_GROUPS)["status"], "ok")
        with hosted_rerank([(0, -3.2)]):
            self.assertEqual(self.pipe.retrieve("q", user=LEAD, groups=LEAD_GROUPS)["status"], "insufficient_context")

    def test_threshold_env_override(self) -> None:
        with hosted_rerank([(0, -7.0)]):
            self.assertEqual(self.pipe.retrieve("q", user=LEAD, groups=LEAD_GROUPS)["status"], "insufficient_context")
        with hosted_rerank([(0, -7.0)]), patch.dict(os.environ, {"AKF_RERANK_MIN_LOGIT": "-8"}):
            self.assertEqual(self.pipe.retrieve("q", user=LEAD, groups=LEAD_GROUPS)["status"], "ok")

    def test_no_permitted_chunks_no_call(self) -> None:
        def boom(q, p):
            raise AssertionError("must not be called")
        with patch.object(rerank_mod, "remote_enabled", lambda: True), patch.object(rerank_mod, "rerank_remote", boom):
            out = self.pipe.retrieve("q", user="nobody@example.com", groups=set())
        self.assertEqual(out["status"], "insufficient_context")
        self.assertEqual(out["citations"], [])
        self.assertEqual(out["rerank_source"], "none")
        self.assertIsNone(out["top_rerank_score"])
        self.assertIsNone(out["rerank_gap"])

    def test_offline_rule_matches_old_skill_rule(self) -> None:
        out = self.pipe.retrieve("How should the workshop evaluate retrieval quality?", user=DEV, groups=DEV_GROUPS)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["rerank_source"], "lexical")
        refused = self.pipe.retrieve("When should enterprise incidents be escalated?", user=DEV, groups=DEV_GROUPS)
        self.assertEqual(refused["status"], "insufficient_context")


if __name__ == "__main__":
    unittest.main()
