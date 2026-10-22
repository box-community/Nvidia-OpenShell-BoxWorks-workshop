from __future__ import annotations

import os as _os

_os.environ.pop("BOX_FOLDER_ID", None)  # these tests use the local sample_box, never live Box

import unittest
from pathlib import Path

from akf_workshop.agent import AgentHarness


ROOT = Path(__file__).resolve().parents[1] / "sample_box"


class RetrievalTests(unittest.TestCase):
    def test_retrieval_returns_citations(self) -> None:
        harness = AgentHarness(ROOT)
        harness.ingest()
        response = harness.ask(
            "How should the workshop evaluate retrieval quality?",
            user="dev@example.com",
            groups={"workshop-attendees"},
        )
        names = {citation["name"] for citation in response["citations"]}
        self.assertEqual(response["status"], "ok")
        self.assertIn("box-ai-retrieval.md", names)

    def test_acl_blocks_restricted_policy(self) -> None:
        harness = AgentHarness(ROOT)
        harness.ingest()
        response = harness.ask(
            "When should enterprise incidents be escalated?",
            user="dev@example.com",
            groups={"workshop-attendees"},
        )
        names = {citation["name"] for citation in response["citations"]}
        self.assertNotIn("enterprise-support-policy.md", names)

    def test_support_lead_can_retrieve_policy(self) -> None:
        harness = AgentHarness(ROOT)
        harness.ingest()
        response = harness.ask(
            "When should enterprise incidents be escalated?",
            user="support-lead@example.com",
            groups={"support-leads"},
        )
        names = {citation["name"] for citation in response["citations"]}
        self.assertIn("enterprise-support-policy.md", names)


if __name__ == "__main__":
    unittest.main()
