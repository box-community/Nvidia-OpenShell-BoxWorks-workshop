from __future__ import annotations

import unittest
from pathlib import Path

from akf_workshop.box_source import BoxPlaceholderAdapter


ROOT = Path(__file__).resolve().parents[1] / "sample_box"


class AdapterTests(unittest.TestCase):
    def test_lists_files_with_stable_metadata(self) -> None:
        adapter = BoxPlaceholderAdapter(ROOT)
        files = adapter.list_files()
        self.assertGreaterEqual(len(files), 5)
        first = files[0]
        self.assertTrue(first.file_id.startswith("box-"))
        self.assertTrue(first.path.startswith("/Box Placeholder/"))
        self.assertTrue(first.version.startswith("v"))

    def test_permission_override_is_preserved(self) -> None:
        adapter = BoxPlaceholderAdapter(ROOT)
        policy = next(file for file in adapter.list_files() if file.name == "enterprise-support-policy.md")
        self.assertIn("support-leads", policy.acl.groups)
        self.assertNotIn("workshop-attendees", policy.acl.groups)


if __name__ == "__main__":
    unittest.main()
