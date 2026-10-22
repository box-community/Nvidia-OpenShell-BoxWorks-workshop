from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from akf_workshop.akf_search.pages import PdfSupportMissing, page_images, pdf_page_count
from akf_workshop.box_source.schema import AccessControl, BoxFile

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PDF_BYTES = FIXTURES.joinpath("one_page.pdf").read_bytes()
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

try:
    import pypdfium2  # noqa: F401
    import PIL  # noqa: F401
    HAS_PDFIUM = True
except ImportError:  # pragma: no cover
    HAS_PDFIUM = False


def _boxfile(name: str, mime: str, data: bytes) -> BoxFile:
    return BoxFile(file_id="box-test", name=name, path=f"/Box Placeholder/docs/{name}", relative_path=f"docs/{name}",
                   mime_type=mime, version="v1", owner="o@example.com", modified_at="2026-10-17T00:00:00Z",
                   labels=("docs",), acl=AccessControl(groups=("workshop-attendees",)), content_bytes=data)


png_boxfile = _boxfile("scan.png", "image/png", PNG_BYTES)
pdf_boxfile = _boxfile("one_page.pdf", "application/pdf", PDF_BYTES)


class PagesTests(unittest.TestCase):
    def test_image_passthrough(self) -> None:
        self.assertEqual(page_images(png_boxfile), [(PNG_BYTES, "image/png")])

    @unittest.skipUnless(HAS_PDFIUM, "pypdfium2 not installed")
    def test_pdf_renders_under_size_cap(self) -> None:
        pages = page_images(pdf_boxfile, max_bytes=180000)
        self.assertEqual(len(pages), 1)
        self.assertLess(len(pages[0][0]), 180000)
        self.assertEqual(pages[0][1], "image/jpeg")
        self.assertEqual(pages[0][0][:3], b"\xff\xd8\xff")

    @unittest.skipUnless(HAS_PDFIUM, "pypdfium2 not installed")
    def test_small_size_cap_forces_requality_and_downscale(self) -> None:
        pages = page_images(pdf_boxfile, max_bytes=40000)
        self.assertLess(len(pages[0][0]), 40000)

    @unittest.skipUnless(HAS_PDFIUM, "pypdfium2 not installed")
    def test_pdf_page_cap(self) -> None:
        self.assertEqual(page_images(pdf_boxfile, max_pages=0), [])
        self.assertEqual(pdf_page_count(PDF_BYTES), 1)

    def test_missing_pdfium_raises_named_error(self) -> None:
        with patch.dict(sys.modules, {"pypdfium2": None}):
            with self.assertRaises(PdfSupportMissing):
                page_images(pdf_boxfile)
            with self.assertRaises(PdfSupportMissing):
                pdf_page_count(PDF_BYTES)


if __name__ == "__main__":
    unittest.main()
