from __future__ import annotations

import math


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    retrieved = _dedupe(retrieved)
    if not relevant:
        return 1.0 if not retrieved else 0.0
    return len(set(retrieved[:k]).intersection(relevant)) / len(relevant)


def mrr_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    retrieved = _dedupe(retrieved)
    for index, item in enumerate(retrieved[:k], start=1):
        if item in relevant:
            return 1.0 / index
    return 0.0


def ndcg_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    retrieved = _dedupe(retrieved)
    dcg = 0.0
    for index, item in enumerate(retrieved[:k], start=1):
        gain = 1.0 if item in relevant else 0.0
        dcg += gain / math.log2(index + 1)
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    return dcg / idcg if idcg else 1.0


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for item in items:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped
