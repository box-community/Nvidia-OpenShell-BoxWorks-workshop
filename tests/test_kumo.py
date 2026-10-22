from __future__ import annotations

import unittest
from pathlib import Path

from akf_workshop.akf_skills.kumo import KumoPredictionSkill, build_kumo_payload


ROOT = Path(__file__).resolve().parents[1] / "sample_box"


class KumoTests(unittest.TestCase):
    def test_local_prediction_requires_acl(self) -> None:
        skill = KumoPredictionSkill(ROOT)
        denied = skill(query="predict risk", user="dev@example.com", groups={"workshop-attendees"})
        self.assertEqual(denied["status"], "denied")

    def test_local_prediction_returns_evidence(self) -> None:
        skill = KumoPredictionSkill(ROOT)
        result = skill(query="predict risk", user="support-lead@example.com", groups={"support-leads"})
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["evidence"])

    def test_payload_uses_kumo_contract(self) -> None:
        payload = build_kumo_payload(ROOT)
        self.assertEqual(payload["model"], "kumo-relational")
        self.assertEqual(payload["task"]["kind"], "binary_classification")
        self.assertIn("relationships", payload["schema"])
        self.assertIn("predict", payload)


if __name__ == "__main__":
    unittest.main()
