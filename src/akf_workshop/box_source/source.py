"""Pick where files come from: real Box when BOX_FOLDER_ID is set, otherwise the local sample_box folder."""
from __future__ import annotations

import os
from pathlib import Path

from .adapter import BoxPlaceholderAdapter


def make_adapter(sample_box_root: Path | str):
    folder_id = os.getenv("BOX_FOLDER_ID", "").strip()
    if folder_id:
        from .box_api import BoxApiAdapter

        return BoxApiAdapter(folder_id)
    return BoxPlaceholderAdapter(sample_box_root)


def describe_source(adapter) -> str:
    if adapter.__class__.__name__ == "BoxApiAdapter":
        return f"Box folder {adapter.folder_id} (live Box API)"
    return f"local folder {adapter.root} (Box placeholder)"
