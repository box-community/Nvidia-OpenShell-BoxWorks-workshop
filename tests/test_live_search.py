from __future__ import annotations

import unittest
from pathlib import Path

from akf_workshop.akf_search.pipeline import SearchPipeline
from akf_workshop.nvidia_clients import remote_enabled

SAMPLE = Path(__file__).resolve().parents[1] / "sample_box"


@unittest.skipUnless(remote_enabled(), "needs NVIDIA_USE_REMOTE=1 and NVIDIA_API_KEY")
class LiveSearchTests(unittest.TestCase):
    """Five hosted calls in total: one batch embed, two query embeds, two reranks."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pipe = SearchPipeline(SAMPLE)
        cls.pipe.ingest()

    def test_paraphrase_is_answered_for_support_lead(self) -> None:
        out = self.pipe.retrieve("How quickly must we escalate an incident that affects a customer?",
                                 user="support-lead@example.com", groups={"support-leads"})
        print(f"\n  paraphrase: status={out['status']} top={out['top_rerank_score']:.2f} gap={out['rerank_gap']:.2f}")
        self.assertEqual(out["rerank_source"], "hosted")
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["citations"][0]["name"], "enterprise-support-policy.md")

    def test_unanswerable_question_is_refused(self) -> None:
        out = self.pipe.retrieve("What is the warranty on the HX-9000 curing light?",
                                 user="dev@example.com", groups={"workshop-attendees"})
        print(f"\n  no-answer: status={out['status']} top={out['top_rerank_score']:.2f} gap={out['rerank_gap']:.2f}")
        self.assertEqual(out["status"], "insufficient_context")


if __name__ == "__main__":
    unittest.main()
