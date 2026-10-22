from __future__ import annotations

import os as _os

_os.environ.pop("BOX_FOLDER_ID", None)  # these tests use the local sample_box, never live Box

import os
import shutil
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from akf_workshop.akf_search.parse import parse_artifact
from akf_workshop.akf_search.pipeline import SearchPipeline
from akf_workshop.box_source import BoxPlaceholderAdapter

SAMPLE = Path(__file__).resolve().parents[1] / "sample_box"


def _png_1x1() -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b""))


PNG_BYTES = _png_1x1()
PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\n%%EOF\n"


def make_sample_copy_with(files: dict[str, bytes]) -> Path:
    root = Path(tempfile.mkdtemp()) / "sample_box"
    shutil.copytree(SAMPLE, root)
    for relative, data in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return root


class AdapterBytesTests(unittest.TestCase):
    def setUp(self) -> None:
        patch.dict(os.environ, {"NVIDIA_USE_REMOTE": "0"}).start()
        self.addCleanup(patch.stopall)
        self.root = make_sample_copy_with({"docs/scan.png": PNG_BYTES, "docs/contract.pdf": PDF_BYTES})
        self.addCleanup(shutil.rmtree, self.root.parent)

    def test_png_and_pdf_do_not_crash_ingest(self) -> None:
        out = SearchPipeline(self.root).ingest()
        self.assertEqual(out["files"], 7)
        self.assertEqual(len(out["notices"]), 2)
        self.assertEqual(out["chunks"], 11)

    def test_binary_file_carries_bytes_not_text(self) -> None:
        adapter = BoxPlaceholderAdapter(self.root)
        listed = next(f for f in adapter.list_files() if f.name == "scan.png")
        full = adapter.get_file(listed.file_id)
        self.assertEqual(full.content, "")
        self.assertEqual(full.content_bytes[:4], b"\x89PNG")

    def test_text_file_still_carries_text(self) -> None:
        adapter = BoxPlaceholderAdapter(self.root)
        listed = next(f for f in adapter.list_files() if f.name == "accounts.csv")
        full = adapter.get_file(listed.file_id)
        self.assertTrue(full.content.startswith("account_id"))
        self.assertEqual(full.content_bytes, b"")

    def test_unknown_extension_binary_does_not_crash(self) -> None:
        root = make_sample_copy_with({"data/budget.numbers": b"\x00\x01\x89\xfe\xff binary", "data/model.parquet": b"PAR1\x89\xfe\xffPAR1"})
        self.addCleanup(shutil.rmtree, root.parent)
        out = SearchPipeline(root).ingest()
        self.assertEqual(out["files"], 7)
        self.assertEqual(len(out["notices"]), 2)

    def test_offline_binary_becomes_notice_section(self) -> None:
        adapter = BoxPlaceholderAdapter(self.root)
        listed = next(f for f in adapter.list_files() if f.name == "scan.png")
        sections = parse_artifact(adapter.get_file(listed.file_id), self.root)
        self.assertEqual([s.kind for s in sections], ["notice"])
        self.assertIn("not parsed offline", sections[0].text)
        self.assertIn("scan.png", sections[0].text)


if __name__ == "__main__":
    unittest.main()
