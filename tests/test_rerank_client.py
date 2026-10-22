from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from akf_workshop import nvidia_clients

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PASSAGES = [
    "The catalog lists HX-4410 with a two-year warranty.",
    "Enterprise incidents with customer impact should be escalated to the support lead within 30 minutes.",
    "Chunk size should be treated as a quality and cost knob.",
]


class RerankClientTests(unittest.TestCase):
    def setUp(self) -> None:
        patch.dict(os.environ, {"NVIDIA_USE_REMOTE": "0"}).start()
        self.addCleanup(patch.stopall)

    def test_posts_expected_body_and_returns_sorted_pairs(self) -> None:
        seen = {}

        def fake_post(url, payload):
            seen["url"], seen["payload"] = url, payload
            return json.loads(FIXTURES.joinpath("rerank_response.json").read_text())

        with patch.object(nvidia_clients, "_post_json", fake_post):
            pairs = nvidia_clients.rerank_remote("When should enterprise incidents be escalated?", PASSAGES)
        self.assertEqual(seen["payload"]["query"], {"text": "When should enterprise incidents be escalated?"})
        self.assertEqual(seen["payload"]["passages"], [{"text": p} for p in PASSAGES])
        self.assertEqual(seen["payload"]["truncate"], "END")
        self.assertEqual(seen["payload"]["model"], "nvidia/nemotron-3.5-rerank-8b")
        self.assertTrue(seen["url"].endswith("/nemotron-3.5-rerank-8b/reranking"))
        self.assertEqual([i for i, _ in pairs], [1, 2, 0])
        self.assertGreater(pairs[0][1], pairs[1][1])

    def test_unsorted_response_is_sorted_client_side(self) -> None:
        unsorted = {"rankings": [{"index": 0, "logit": -9.0}, {"index": 1, "logit": 5.0}]}
        with patch.object(nvidia_clients, "_post_json", lambda u, p: unsorted):
            self.assertEqual(nvidia_clients.rerank_remote("q", ["a", "b"]), [(1, 5.0), (0, -9.0)])

    def test_short_rankings_raise(self) -> None:
        with patch.object(nvidia_clients, "_post_json", lambda u, p: {"rankings": [{"index": 0, "logit": 1.0}]}):
            with self.assertRaises(ValueError):
                nvidia_clients.rerank_remote("q", ["a", "b"])

    def test_malformed_rankings_raise_value_error(self) -> None:
        for body in ({"rankings": [{"index": 0, "score": 1.0}, {"index": 1, "score": 0.5}]}, {"rankings": None}, {"data": []}, []):
            with patch.object(nvidia_clients, "_post_json", lambda u, p, body=body: body):
                with self.assertRaises(ValueError, msg=repr(body)):
                    nvidia_clients.rerank_remote("q", ["a", "b"])

    def test_duplicate_indices_raise(self) -> None:
        with patch.object(nvidia_clients, "_post_json", lambda u, p: {"rankings": [{"index": 0, "logit": 1.0}, {"index": 0, "logit": 0.5}]}):
            with self.assertRaises(ValueError):
                nvidia_clients.rerank_remote("q", ["a", "b"])

    def test_out_of_range_index_raises(self) -> None:
        bad = {"rankings": [{"index": 0, "logit": 1.0}, {"index": 7, "logit": 0.5}]}
        with patch.object(nvidia_clients, "_post_json", lambda u, p: bad):
            with self.assertRaises(ValueError):
                nvidia_clients.rerank_remote("q", ["a", "b"])


if __name__ == "__main__":
    unittest.main()
