"""Exact cosine search with a permission mask.

The mask is an index-aligned list of booleans: rows the user may not see are dropped before the
top-k is chosen, so restricted chunks are never scored.
"""
from __future__ import annotations

import math


def cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or not right:
        return 0.0
    length = min(len(left), len(right))
    dot = sum(left[i] * right[i] for i in range(length))
    left_norm = math.sqrt(sum(value * value for value in left[:length])) or 1.0
    right_norm = math.sqrt(sum(value * value for value in right[:length])) or 1.0
    return dot / (left_norm * right_norm)


class ExactIndex:
    """Exact cosine search over a Python list: compares the query with every permitted vector."""

    def __init__(self) -> None:
        self.vectors: list[tuple[float, ...]] = []

    def build(self, vectors: list[tuple[float, ...]]) -> None:
        self.vectors = [tuple(vector) for vector in vectors]

    def search(self, query: tuple[float, ...], k: int, allowed: list[bool]) -> list[tuple[int, float]]:
        scored = [(row, cosine(query, vector)) for row, vector in enumerate(self.vectors) if row < len(allowed) and allowed[row]]
        return sorted(scored, key=lambda pair: pair[1], reverse=True)[:k]
