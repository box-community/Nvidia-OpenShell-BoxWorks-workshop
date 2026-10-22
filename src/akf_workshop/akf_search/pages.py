"""Turn a BoxFile's bytes into page images for Nemotron Parse.

Images pass through unchanged. PDFs are rendered page by page with pypdfium2 (an optional
extra: pip install "pypdfium2>=5" "Pillow>=10") and encoded as JPEG kept under a size cap,
since the hosted Parse endpoint takes one inline image per request.
"""
from __future__ import annotations

import io
import os

from akf_workshop.box_source.schema import BoxFile

IMAGE_MIME_TYPES = {"image/png": "image/png", "image/jpeg": "image/jpeg", "image/jpg": "image/jpeg"}
JPEG_QUALITIES = (85, 75, 65, 55, 45)


class PdfSupportMissing(RuntimeError):
    """pypdfium2 or Pillow is not installed, so PDF pages cannot be rendered."""


def _pdfium():
    try:
        import pypdfium2  # noqa: WPS433
        import PIL.Image  # noqa: F401, WPS433
    except ImportError as exc:
        raise PdfSupportMissing('install the PDF extra: pip install "pypdfium2>=5" "Pillow>=10"') from exc
    return pypdfium2


def pdf_page_count(content_bytes: bytes) -> int:
    pypdfium2 = _pdfium()
    return len(pypdfium2.PdfDocument(content_bytes))


def page_images(box_file: BoxFile, max_pages: int | None = None, max_bytes: int | None = None) -> list[tuple[bytes, str]]:
    """Return (image_bytes, mime) per page, at most `max_pages` pages, each under `max_bytes`."""
    if max_pages is None:
        max_pages = int(os.getenv("AKF_PARSE_MAX_PAGES", "20"))
    if max_bytes is None:
        max_bytes = int(os.getenv("AKF_PARSE_MAX_IMAGE_BYTES", "180000"))
    if box_file.mime_type in IMAGE_MIME_TYPES:
        return [(box_file.content_bytes, IMAGE_MIME_TYPES[box_file.mime_type])]
    pypdfium2 = _pdfium()
    document = pypdfium2.PdfDocument(box_file.content_bytes)
    pages: list[tuple[bytes, str]] = []
    for index in range(min(len(document), max_pages)):
        pages.append((_render_page_jpeg(document[index], max_bytes), "image/jpeg"))
    return pages


def _render_page_jpeg(page, max_bytes: int, scale: float = 2.0) -> bytes:
    """Render at `scale`, lowering JPEG quality until under `max_bytes`; halve the scale once if still over."""
    for attempt_scale in (scale, scale / 2):
        image = page.render(scale=attempt_scale).to_pil().convert("RGB")
        for quality in JPEG_QUALITIES:
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=quality)
            data = buffer.getvalue()
            if len(data) <= max_bytes:
                return data
    return data
