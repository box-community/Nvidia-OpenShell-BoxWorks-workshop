import os as _os

_os.environ.pop("BOX_FOLDER_ID", None)  # these tests use the local sample_box, never live Box

import json
import os
import unittest
from pathlib import Path
from unittest import mock

from akf_workshop.agent import nemotron_agent
from akf_workshop.agent.nemotron_agent import NemotronAgent

SAMPLE = Path(__file__).resolve().parents[1] / "sample_box"
DEV, DEV_GROUPS = "dev@example.com", {"workshop-attendees"}
LEAD, LEAD_GROUPS = "support-lead@example.com", {"support-leads"}


def tool_call(name: str, arguments: dict, call_id: str = "call-1") -> dict:
    return {"content": "", "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]}


class NemotronAgentTest(unittest.TestCase):
    """The model is faked; search, rerank and permissions run offline for real."""

    def setUp(self) -> None:
        # Offline embed and rerank for the pipeline, but let the agent itself run.
        mock.patch.dict(os.environ, {"NVIDIA_USE_REMOTE": "0"}).start()
        mock.patch.object(nemotron_agent, "remote_enabled", return_value=True).start()
        self.addCleanup(mock.patch.stopall)
        self.agent = NemotronAgent(SAMPLE)
        self.agent.ingest()

    def run_with(self, replies: list, query: str, user: str = DEV, groups: set[str] = DEV_GROUPS) -> dict:
        with mock.patch.object(nemotron_agent, "chat_remote", side_effect=replies):
            return self.agent.ask(query, user=user, groups=groups)

    def test_model_searches_then_answers_with_citation(self) -> None:
        question = "How should the workshop evaluate retrieval quality?"
        search = self.agent._run_tool("search_documents", {"query": question}, DEV, DEV_GROUPS, {}, [])
        chunk_id = search["passages"][0]["chunk_id"]
        out = self.run_with([tool_call("search_documents", {"query": question}), {"content": f"Use Recall@k and MRR@k [{chunk_id}]."}], question)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["agent"], "nemotron")
        self.assertEqual([c["chunk_id"] for c in out["citations"]], [chunk_id])
        self.assertIn("tool", [event["name"] for event in out["trace"]["events"]])

    def test_tools_enforce_permissions_whatever_the_model_asks(self) -> None:
        search = self.agent._run_tool("search_documents", {"query": "enterprise incidents escalated support lead 30 minutes"}, DEV, DEV_GROUPS, {}, [])
        self.assertNotIn("enterprise-support-policy.md", [p["file"] for p in search.get("passages", [])])
        prediction = self.agent._run_tool("predict_support_risk", {}, DEV, DEV_GROUPS, {}, [])
        self.assertEqual(prediction["status"], "denied")

    def test_answer_without_citations_is_not_ok(self) -> None:
        question = "How should the workshop evaluate retrieval quality?"
        out = self.run_with([tool_call("search_documents", {"query": question}), {"content": "It probably uses some metrics."}], question)
        self.assertEqual(out["status"], "insufficient_context")
        self.assertEqual(out["citations"], [])

    def test_made_up_chunk_id_is_reported(self) -> None:
        question = "How should the workshop evaluate retrieval quality?"
        out = self.run_with([tool_call("search_documents", {"query": question}), {"content": "Use recall [box-000000000000:9999]."}], question)
        final = [e for e in out["trace"]["events"] if e["name"] == "final"][0]
        self.assertEqual(final["unknown_citations"], ["box-000000000000:9999"])
        self.assertEqual(out["status"], "insufficient_context")

    def test_denied_prediction_for_attendee(self) -> None:
        out = self.run_with([tool_call("predict_support_risk", {}), {"content": "The prediction is restricted to support leads."}], "Which account is most at risk?")
        self.assertEqual(out["status"], "denied")

    def test_support_lead_prediction_counts_as_evidence(self) -> None:
        out = self.run_with([tool_call("predict_support_risk", {}), {"content": "Beacon Health is at high risk."}], "Which account is most at risk?", LEAD, LEAD_GROUPS)
        self.assertEqual(out["status"], "ok")
        self.assertTrue(out["skill_evidence"])

    def test_model_failure_falls_back_to_rule_based_agent(self) -> None:
        error = RuntimeError("NVIDIA API error 500")
        with mock.patch.object(nemotron_agent.time, "sleep"):
            out = self.run_with([error, error, error], "How should the workshop evaluate retrieval quality?")
        self.assertEqual(out["agent"], "rule-based-fallback")
        self.assertEqual(out["status"], "ok")
        self.assertIn("llm_failed", [event["name"] for event in out["trace"]["events"]])

    def test_needs_remote_mode(self) -> None:
        with mock.patch.object(nemotron_agent, "remote_enabled", return_value=False):
            with self.assertRaises(RuntimeError):
                self.agent.ask("anything", user=DEV, groups=DEV_GROUPS)


if __name__ == "__main__":
    unittest.main()
