from __future__ import annotations

import os as _os

_os.environ.pop("BOX_FOLDER_ID", None)  # these tests use the local sample_box, never live Box

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from akf_workshop.akf_search.index import ExactIndex
from akf_workshop.akf_search.pipeline import SearchPipeline

SAMPLE = Path(__file__).resolve().parents[1] / "sample_box"
DEV, DEV_GROUPS = "dev@example.com", {"workshop-attendees"}
VECS = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.9, 0.1, 0.0), (0.0, 0.0, 1.0)]


class IndexTests(unittest.TestCase):
    def setUp(self) -> None:
        patch.dict(os.environ, {"NVIDIA_USE_REMOTE": "0"}).start()
        self.addCleanup(patch.stopall)

    def test_exact_matches_previous_ordering(self) -> None:
        idx = ExactIndex()
        idx.build(VECS)
        self.assertEqual([row for row, _ in idx.search(VECS[0], 3, [True] * 4)], [0, 2, 1])

    def test_allowed_mask_excludes_rows(self) -> None:
        idx = ExactIndex()
        idx.build(VECS)
        rows = [row for row, _ in idx.search(VECS[0], 4, [False, True, True, True])]
        self.assertNotIn(0, rows)
        self.assertEqual(rows[0], 2)

    def test_pipeline_never_returns_restricted_chunks(self) -> None:
        pipe = SearchPipeline(SAMPLE)
        pipe.ingest()
        out = pipe.retrieve("When should enterprise incidents be escalated?", user=DEV, groups=DEV_GROUPS)
        self.assertNotIn("enterprise-support-policy.md", [c["name"] for c in out["citations"]])


if __name__ == "__main__":
    unittest.main()
