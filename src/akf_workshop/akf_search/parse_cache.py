"""On-disk cache for parsed sections, keyed by content hash, model and prompt.

The CLI rebuilds the index on every command, so without this every run would re-parse every page.
Directory: $AKF_CACHE_DIR (default .akf_cache) / parsed. `get` returns None for "no entry" and []
for a cached empty result, so callers must test `is not None`.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def _directory() -> Path:
    return Path(os.getenv("AKF_CACHE_DIR", ".akf_cache")) / "parsed"


def key_for(content_bytes: bytes, model: str, prompt: str, extra: str = "") -> str:
    digest = hashlib.sha1()
    digest.update(content_bytes)
    digest.update(b"\n")
    digest.update(f"{model}\n{prompt}\n{extra}".encode("utf-8"))
    return digest.hexdigest()


def get(key: str) -> list[dict] | None:
    path = _directory() / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # a half-written or corrupt entry is treated as a miss and removed
        try:
            path.unlink()
        except OSError:
            pass
        return None


def put(key: str, sections: list[dict]) -> None:
    directory = _directory()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{key}.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(sections, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temporary, path)
