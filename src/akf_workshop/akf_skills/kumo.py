from __future__ import annotations

import csv
import io
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from akf_workshop.nvidia_clients import kumo_predict_remote, remote_enabled


@dataclass
class KumoPredictionSkill:
    """Reads the two tables through `adapter` (local placeholder or live Box) when one is given.

    Access follows the permissions on support_cases.csv: whoever may see that file may get a prediction.
    """

    sample_box_root: Path
    adapter: Any = None

    def __call__(self, query: str, user: str, groups: set[str]) -> dict[str, Any]:
        start = time.perf_counter()
        source = self.adapter or self.sample_box_root
        allowed = _find(self.adapter, "support_cases.csv").acl.allows(user, groups) if self.adapter else _can_access_support_data(user, groups)
        if not allowed:
            return {
                "skill": "kumo_prediction",
                "status": "denied",
                "answer": "The prediction data is restricted to support leads.",
                "evidence": [],
                "trace_ms": round((time.perf_counter() - start) * 1000, 2),
                "production_swap": "Use Box permissions and Kumo Relational with the same ACL guard.",
            }

        if remote_enabled():
            payload = build_kumo_payload(source)
            response = kumo_predict_remote(payload)
            return {
                "skill": "kumo_prediction",
                "status": "ok",
                "answer": _describe_remote_prediction(source, payload, response),
                "evidence": [{"name": "kumo-relational", "response": response}],
                "trace_ms": round((time.perf_counter() - start) * 1000, 2),
                "production_swap": "Already using NVIDIA Kumo Relational hosted endpoint.",
            }

        result = local_predict_support_risk(source)
        return {
            "skill": "kumo_prediction",
            "status": "ok",
            "answer": result["summary"],
            "evidence": result["evidence"],
            "trace_ms": round((time.perf_counter() - start) * 1000, 2),
            "production_swap": "Swap deterministic scoring for NVIDIA Kumo Relational predictions.",
        }


def local_predict_support_risk(root: Path | Any) -> dict[str, Any]:
    """`root` is the local sample_box folder or a file adapter."""
    accounts = _rows(root, "accounts.csv")
    cases = _rows(root, "support_cases.csv")
    open_cases_by_account: dict[str, list[dict[str, str]]] = {}
    for case in cases:
        if case["status"] == "open":
            open_cases_by_account.setdefault(case["account_id"], []).append(case)

    scored = []
    for account in accounts:
        open_cases = open_cases_by_account.get(account["account_id"], [])
        priority_cases = [case for case in open_cases if case["priority"] in {"P1", "P2"}]
        max_age = max([int(case["age_days"]) for case in open_cases] or [0])
        score = 0.15 * len(open_cases) + 0.2 * len(priority_cases) + 0.02 * max_age
        if account["tier"] == "enterprise":
            score += 0.15
        if int(account["renewal_days"]) <= 21:
            score += 0.15
        scored.append((score, account, open_cases))

    score, account, open_cases = max(scored, key=lambda item: item[0])
    risk = "high" if score >= 0.85 else "medium" if score >= 0.45 else "low"
    evidence = [
        {
            "name": "accounts.csv",
            "path": _path(root, "accounts.csv"),
            "account": account,
        },
        {
            "name": "support_cases.csv",
            "path": _path(root, "support_cases.csv"),
            "open_case_count": len(open_cases),
            "max_case_age_days": max([int(case["age_days"]) for case in open_cases] or [0]),
        },
    ]
    return {
        "summary": f"{account['account_name']} has {risk} predicted support risk with score {score:.2f}.",
        "evidence": evidence,
    }


def build_kumo_payload(root: Path | Any) -> dict[str, Any]:
    accounts = _rows(root, "accounts.csv")
    cases = _rows(root, "support_cases.csv")
    rows = []
    related = []
    for idx, account in enumerate(accounts):
        open_count = sum(1 for case in cases if case["account_id"] == account["account_id"] and case["status"] == "open")
        is_risky = open_count >= 3 or int(account["renewal_days"]) <= 14
        rows.append([idx, "2026-10-05T00:00:00Z", int(account["account_id"]), is_risky])
        related.append([idx, int(account["account_id"]), account["tier"], int(account["renewal_days"]), open_count])
    predict_id = len(rows)
    return {
        "model": "kumo-relational",
        "task": {
            "kind": "binary_classification",
            "target": {
                "column_name": "label",
                "dtype": "bool",
                "classes": ["false", "true"],
                "positive_class": "true",
            },
            "entity_table_names": ["accounts"],
            "anchor_time_column": "anchor_time",
        },
        "schema": {
            "instance_table": {
                "columns": {
                    "instance_id": {"dtype": "int64", "stype": "ID", "nullable": False},
                    "anchor_time": {"dtype": "timestamp[us]", "stype": "timestamp", "nullable": False},
                    "account_id": {"dtype": "int64", "stype": "ID", "nullable": False},
                    "label": {"dtype": "bool", "stype": "categorical"},
                },
                "primary_key": "instance_id",
            },
            "related_tables": {
                "accounts": {
                    "columns": {
                        "instance_id": {"dtype": "int64", "stype": "ID", "nullable": False},
                        "account_id": {"dtype": "int64", "stype": "ID", "nullable": False},
                        "tier": {"dtype": "string", "stype": "categorical"},
                        "renewal_days": {"dtype": "int64", "stype": "numerical"},
                        "open_cases": {"dtype": "int64", "stype": "numerical"},
                    },
                    "primary_key": ["instance_id", "account_id"],
                }
            },
            "relationships": [
                {
                    "source_columns": ["instance_id", "account_id"],
                    "target_table": "accounts",
                    "target_columns": ["instance_id", "account_id"],
                }
            ],
        },
        "context": {
            "instance_table": {
                "format": "arrays",
                "columns": ["instance_id", "anchor_time", "account_id", "label"],
                "rows": rows,
            },
            "related_tables": {
                "accounts": {
                    "format": "arrays",
                    "columns": ["instance_id", "account_id", "tier", "renewal_days", "open_cases"],
                    "rows": related,
                }
            },
        },
        "predict": {
            "instance_table": {
                "format": "arrays",
                "columns": ["instance_id", "anchor_time", "account_id"],
                "rows": [[predict_id, "2026-10-05T00:00:00Z", 101]],
            },
            "related_tables": {
                "accounts": {
                    "format": "arrays",
                    "columns": ["instance_id", "account_id", "tier", "renewal_days", "open_cases"],
                    "rows": [[predict_id, 101, "enterprise", 8, 3]],
                }
            },
        },
        "output": {"fields": ["prediction", "probabilities"]},
    }


def _describe_remote_prediction(root: Path | Any, payload: dict[str, Any], response: dict[str, Any]) -> str:
    """Name the account the hosted model scored: its response identifies rows only by index."""
    try:
        account_id = str(payload["predict"]["instance_table"]["rows"][0][2])
        prediction = response["predictions"][0]
        probability = float(prediction["probabilities"]["true"])
    except (KeyError, IndexError, TypeError, ValueError):
        return "Kumo Relational returned a remote prediction response."
    names = {row["account_id"]: row["account_name"] for row in _rows(root, "accounts.csv")}
    risk = "high" if prediction.get("prediction") is True else "low"
    return f"Kumo Relational predicts {risk} support risk for {names.get(account_id, 'account')} (account {account_id}), probability {probability:.4f}."


def _rows(source: Path | Any, name: str) -> list[dict[str, str]]:
    """Rows of a table, from the local data/ folder or from the file adapter (local placeholder or live Box)."""
    if isinstance(source, (str, Path)):
        return _read_csv(Path(source) / "data" / name)
    box_file = source.get_file(_find(source, name).file_id)
    return list(csv.DictReader(io.StringIO(box_file.content)))


def _path(source: Path | Any, name: str) -> str:
    return f"/Box Placeholder/data/{name}" if isinstance(source, (str, Path)) else _find(source, name).path


def _find(adapter: Any, name: str):
    for box_file in adapter.list_files():
        if box_file.name == name:
            return box_file
    raise FileNotFoundError(f"{name} not found in the file source")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _can_access_support_data(user: str, groups: set[str]) -> bool:
    return user == "support-lead@example.com" or "support-leads" in groups
