from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from akf_workshop.akf_search import parse_cache


class ParseCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cache_dir = tempfile.mkdtemp()
        patch.dict(os.environ, {"AKF_CACHE_DIR": self.cache_dir}).start()
        self.addCleanup(patch.stopall)
        self.addCleanup(shutil.rmtree, self.cache_dir, True)

    def test_round_trip_and_no_temp_files_left(self) -> None:
        key = parse_cache.key_for(b"bytes", "model", "prompt")
        parse_cache.put(key, [{"heading": "h", "text": "t", "kind": "text"}])
        self.assertEqual(parse_cache.get(key), [{"heading": "h", "text": "t", "kind": "text"}])
        self.assertEqual([p.name for p in Path(self.cache_dir).rglob("*.tmp")], [])

    def test_missing_entry_is_none_and_empty_list_is_cached(self) -> None:
        key = parse_cache.key_for(b"x", "m", "p")
        self.assertIsNone(parse_cache.get(key))
        parse_cache.put(key, [])
        self.assertEqual(parse_cache.get(key), [])

    def test_corrupt_entry_is_ignored_and_removed(self) -> None:
        key = parse_cache.key_for(b"x", "m", "p")
        path = Path(self.cache_dir) / "parsed" / f"{key}.json"
        path.parent.mkdir(parents=True)
        path.write_text("[{\"heading\": \"truncated")
        self.assertIsNone(parse_cache.get(key))
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
