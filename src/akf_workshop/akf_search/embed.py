from __future__ import annotations

import hashlib
import math
import re

from akf_workshop.nvidia_clients import embed_texts_remote, remote_enabled


TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def embed_texts(texts: list[str], input_type: str, dimensions: int = 64) -> list[tuple[float, ...]]:
    if remote_enabled():
        return [tuple(vector) for vector in embed_texts_remote(texts, input_type=input_type)]
    return [_local_embedding(text, dimensions) for text in texts]


def _local_embedding(text: str, dimensions: int) -> tuple[float, ...]:
    vector = [0.0] * dimensions
    for token in TOKEN_RE.findall(text.lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % dimensions
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return tuple(value / norm for value in vector)
