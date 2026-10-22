from __future__ import annotations

import unittest

from akf_workshop.evals import mrr_at_k, ndcg_at_k, recall_at_k


class MetricTests(unittest.TestCase):
    def test_metrics(self) -> None:
        retrieved = ["a.md", "b.md", "c.md"]
        relevant = {"b.md", "d.md"}
        self.assertEqual(recall_at_k(retrieved, relevant, 3), 0.5)
        self.assertEqual(mrr_at_k(retrieved, relevant, 3), 0.5)
        self.assertGreater(ndcg_at_k(retrieved, relevant, 3), 0)


if __name__ == "__main__":
    unittest.main()
