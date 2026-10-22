from __future__ import annotations

import argparse
import json
from pathlib import Path

from akf_workshop.agent import AgentHarness

from .retrieval_metrics import mrr_at_k, ndcg_at_k, recall_at_k


def main() -> int:
    parser = argparse.ArgumentParser(description="Run workshop retrieval evals")
    parser.add_argument("--sample-box", default="sample_box")
    parser.add_argument("--golden", default="src/akf_workshop/evals/golden_questions.json")
    parser.add_argument("--summary", action="store_true", help="Print one line per question instead of JSON")
    args = parser.parse_args()

    harness = AgentHarness(Path(args.sample_box))
    harness.ingest()
    questions = json.loads(Path(args.golden).read_text(encoding="utf-8"))
    rows = []
    for item in questions:
        response = harness.ask(item["question"], user=item["user"], groups=set(item["groups"]))
        retrieved_files = [citation["name"] for citation in response["citations"]]
        relevant = set(item["expected_files"])
        rows.append(
            {
                "question": item["question"],
                "user": item["user"],
                "status": response["status"],
                "expected_status": item["expect_status"],
                "retrieved_files": retrieved_files,
                "recall@3": round(recall_at_k(retrieved_files, relevant, 3), 3),
                "mrr@3": round(mrr_at_k(retrieved_files, relevant, 3), 3),
                "ndcg@3": round(ndcg_at_k(retrieved_files, relevant, 3), 3),
                "status_pass": response["status"] == item["expect_status"],
            }
        )
    if args.summary:
        print_summary(rows)
    else:
        print(json.dumps({"results": rows}, indent=2))
    return 0


def print_summary(rows: list[dict]) -> None:
    for row in rows:
        mark = "PASS" if row["status_pass"] else "FAIL"
        got = row["status"] if row["status_pass"] else f"{row['status']} (expected {row['expected_status']})"
        who = row["user"].split("@")[0]
        print(f"{mark}  recall@3 {row['recall@3']:.2f}  {got:46}  {who:13} {row['question']}")
    passed = sum(row["status_pass"] for row in rows)
    recall = sum(row["recall@3"] for row in rows) / max(len(rows), 1)
    print(f"\n{passed} of {len(rows)} status checks passed · average recall@3 {recall:.2f}")


if __name__ == "__main__":
    raise SystemExit(main())
