from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from akf_workshop.akf_search import parse as parse_mod
from akf_workshop.akf_search.parse import parse_artifact
from akf_workshop.box_source.schema import AccessControl, BoxFile

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FIXTURE_RAW = FIXTURES.joinpath("parse2_response.txt").read_text()
FIXTURE_V1 = FIXTURES.joinpath("parse1_response.json").read_text()
PDF_BYTES = FIXTURES.joinpath("one_page.pdf").read_bytes()
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

try:
    import pypdfium2  # noqa: F401
    import PIL  # noqa: F401
    HAS_PDFIUM = True
except ImportError:  # pragma: no cover
    HAS_PDFIUM = False


def _boxfile(name: str, mime: str, data: bytes) -> BoxFile:
    return BoxFile(file_id="box-" + name, name=name, path=f"/Box Placeholder/docs/{name}", relative_path=f"docs/{name}",
                   mime_type=mime, version="v1", owner="o@example.com", modified_at="2026-10-17T00:00:00Z",
                   labels=("docs",), acl=AccessControl(groups=("support-leads",)), content_bytes=data)


pdf_boxfile = _boxfile("one_page.pdf", "application/pdf", PDF_BYTES)
png_boxfile = _boxfile("scan.png", "image/png", PNG_BYTES)


class ParseRemoteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cache_dir = tempfile.mkdtemp()
        patch.dict(os.environ, {"NVIDIA_USE_REMOTE": "1", "NVIDIA_API_KEY": "nvapi-test", "AKF_CACHE_DIR": self.cache_dir}).start()
        self.addCleanup(patch.stopall)
        self.addCleanup(shutil.rmtree, self.cache_dir, True)

    @unittest.skipUnless(HAS_PDFIUM, "pypdfium2 not installed")
    def test_pdf_goes_through_pages_parse_and_cache(self) -> None:
        calls = []
        with patch.object(parse_mod, "parse_image_remote", lambda img, **kw: calls.append(kw.get("mime")) or FIXTURE_RAW):
            first = parse_artifact(pdf_boxfile)
            second = parse_artifact(pdf_boxfile)
        self.assertEqual(calls, ["image/jpeg"])
        self.assertEqual(first, second)
        self.assertGreater(len(first), 0)
        self.assertEqual(first[0].kind, "text")
        self.assertEqual(first[0].acl, pdf_boxfile.acl)

    def test_missing_pdfium_gives_notice_not_crash(self) -> None:
        with patch.dict(sys.modules, {"pypdfium2": None}):
            secs = parse_artifact(pdf_boxfile)
        self.assertEqual([s.kind for s in secs], ["notice"])
        self.assertIn("pypdfium2", secs[0].text)
        self.assertIn("one_page.pdf", secs[0].text)

    def test_hosted_parse_failure_becomes_notice_and_is_not_cached(self) -> None:
        calls = []

        def boom(img, **kw):
            calls.append(1)
            raise RuntimeError("NVIDIA API error 429: rate limited")

        with patch.object(parse_mod, "parse_image_remote", boom):
            first = parse_artifact(png_boxfile)
            second = parse_artifact(png_boxfile)
        self.assertEqual([s.kind for s in first], ["notice"])
        self.assertIn("scan.png", first[0].text)
        self.assertIn("page 1", first[0].text)
        self.assertEqual(len(calls), 2, "a failed parse must not be cached")
        self.assertEqual(first, second)

    def test_unsupported_binary_type_becomes_notice(self) -> None:
        docx = _boxfile("deck.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"PK\x03\x04junk")

        def boom(img, **kw):
            raise AssertionError("must not be called")

        with patch.object(parse_mod, "parse_image_remote", boom):
            secs = parse_artifact(docx)
        self.assertEqual([s.kind for s in secs], ["notice"])
        self.assertIn("deck.docx", secs[0].text)
        self.assertIn("Unsupported", secs[0].text)

    @unittest.skipUnless(HAS_PDFIUM, "pypdfium2 not installed")
    def test_malformed_pdf_becomes_notice(self) -> None:
        broken = _boxfile("broken.pdf", "application/pdf", b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\n%%EOF\n")
        secs = parse_artifact(broken)
        self.assertEqual([s.kind for s in secs], ["notice"])
        self.assertIn("broken.pdf", secs[0].text)

    def test_empty_parse2_falls_back_to_v1_and_caches(self) -> None:
        calls = []
        with patch.object(parse_mod, "parse_image_remote", lambda img, **kw: calls.append("v2") or ""), \
             patch.object(parse_mod, "parse_image_remote_v1", lambda img, **kw: calls.append("v1") or FIXTURE_V1):
            first = parse_artifact(png_boxfile)
            second = parse_artifact(png_boxfile)
        self.assertEqual(calls, ["v2", "v1"], "v1 is tried once after an empty 2.0 answer; the result is cached")
        self.assertGreater(len(first), 0)
        self.assertEqual([s.kind for s in first], ["text", "text", "text"])
        self.assertEqual(first, second)

    def test_blank_page_becomes_notice_and_is_not_cached(self) -> None:
        calls = []
        with patch.object(parse_mod, "parse_image_remote", lambda img, **kw: calls.append("v2") or ""), \
             patch.object(parse_mod, "parse_image_remote_v1", lambda img, **kw: calls.append("v1") or ""):
            first = parse_artifact(png_boxfile)
            second = parse_artifact(png_boxfile)
        self.assertEqual([s.kind for s in first], ["notice"])
        self.assertIn("no content", first[0].text)
        self.assertIn("scan.png", first[0].text)
        self.assertIn("page 1", first[0].text)
        self.assertEqual(calls, ["v2", "v1", "v2", "v1"], "an empty page must not be cached")
        self.assertEqual(first, second)

    @unittest.skipUnless(HAS_PDFIUM, "pypdfium2 not installed")
    def test_page_cap_notice(self) -> None:
        with patch.dict(os.environ, {"AKF_PARSE_MAX_PAGES": "0"}), \
             patch.object(parse_mod, "parse_image_remote", lambda img, **kw: FIXTURE_RAW):
            secs = parse_artifact(pdf_boxfile)
        self.assertEqual([s.kind for s in secs], ["notice"])
        self.assertIn("Parsed first 0 of 1", secs[0].text)

    def test_text_files_still_use_local_parser_in_remote_mode(self) -> None:
        md = BoxFile(file_id="box-md", name="a.md", path="/Box Placeholder/docs/a.md", relative_path="docs/a.md", mime_type="text/markdown",
                     version="v1", owner="o@example.com", modified_at="2026-10-17T00:00:00Z", labels=("docs",), acl=AccessControl(), content="# H\n\nbody")
        secs = parse_artifact(md)
        self.assertEqual(secs[0].heading, "H")


if __name__ == "__main__":
    unittest.main()
