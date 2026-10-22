from __future__ import annotations

import csv
import os
from pathlib import Path

from akf_workshop.box_source.schema import BoxFile
from akf_workshop.nvidia_clients import PARSE2_PROMPT, parse_image_remote, parse_image_remote_v1, remote_enabled

from . import parse_cache
from .pages import IMAGE_MIME_TYPES, PdfSupportMissing, page_images, pdf_page_count
from .parse_postprocess import elements_from_response, elements_from_v1_response, elements_to_sections
from .schema import ParsedSection


def parse_artifact(box_file: BoxFile, local_root: Path | None = None) -> list[ParsedSection]:
    """Text files are split locally; binaries go to Nemotron Parse page by page when remote mode is on."""
    if not box_file.content and box_file.content_bytes:
        if remote_enabled():
            return _parse_binary_remote(box_file)
        notice = f"Binary file not parsed offline: {box_file.name} ({box_file.mime_type})"
        return [_section(box_file, "Notice", notice, kind="notice")]
    if box_file.name.endswith(".csv"):
        return [_section(box_file, "CSV table", _summarize_csv(box_file.content))]
    return _parse_markdown(box_file)


def _parse_markdown(box_file: BoxFile) -> list[ParsedSection]:
    sections: list[ParsedSection] = []
    heading = box_file.name
    lines: list[str] = []
    for raw in box_file.content.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            if lines:
                sections.append(_section(box_file, heading, "\n".join(lines).strip()))
                lines = []
            heading = line.lstrip("#").strip() or box_file.name
        elif line:
            lines.append(line)
    if lines:
        sections.append(_section(box_file, heading, "\n".join(lines).strip()))
    return sections or [_section(box_file, box_file.name, box_file.content)]


def _summarize_csv(content: str) -> str:
    rows = list(csv.reader(content.splitlines()))
    if not rows:
        return ""
    header = rows[0]
    sample = rows[1:4]
    return f"Columns: {', '.join(header)}\nSample rows: {sample}\nRow count: {max(len(rows) - 1, 0)}"


def _section(box_file: BoxFile, heading: str, text: str, kind: str = "text") -> ParsedSection:
    return ParsedSection(
        file_id=box_file.file_id,
        heading=heading,
        text=text,
        source_name=box_file.name,
        source_path=box_file.path,
        source_version=box_file.version,
        labels=box_file.labels,
        acl=box_file.acl,
        kind=kind,
    )


def _parse_binary_remote(box_file: BoxFile) -> list[ParsedSection]:
    """Parse a PDF or image through Nemotron Parse. Every failure becomes a notice, never a crash."""
    name = box_file.name
    if box_file.mime_type != "application/pdf" and box_file.mime_type not in IMAGE_MIME_TYPES:
        return [_section(box_file, "Notice", f"Unsupported binary type, not parsed: {name} ({box_file.mime_type})", kind="notice")]
    model = os.getenv("NVIDIA_PARSE_MODEL", "nvidia/nemotron-parse-2.0")
    max_pages = int(os.getenv("AKF_PARSE_MAX_PAGES", "20"))
    key = parse_cache.key_for(box_file.content_bytes, model, PARSE2_PROMPT, extra=str(max_pages))
    cached = parse_cache.get(key)
    if cached is not None:
        return [_section(box_file, item["heading"], item["text"], item["kind"]) for item in cached]
    try:
        pages = page_images(box_file, max_pages=max_pages)
        total = pdf_page_count(box_file.content_bytes) if box_file.mime_type == "application/pdf" else len(pages)
    except PdfSupportMissing as exc:
        return [_section(box_file, "Notice", f"PDF not parsed ({name}): {exc}", kind="notice")]
    except (RuntimeError, ValueError, OSError) as exc:  # pdfium load errors subclass RuntimeError
        return [_section(box_file, "Notice", f"Document could not be opened ({name}): {type(exc).__name__}: {exc}", kind="notice")]
    sections: list[ParsedSection] = []
    failed = False
    for page_number, (image, mime) in enumerate(pages, start=1):
        try:
            elements = elements_from_response(parse_image_remote(image, mime=mime))
            if not elements:  # Parse 2.0 sometimes returns nothing for a page; v1's markdown_bbox is the fallback
                elements = elements_from_v1_response(parse_image_remote_v1(image, mime=mime))
        except (RuntimeError, ValueError, OSError) as exc:
            failed = True
            sections.append(_section(box_file, "Notice", f"Parse failed for {name} page {page_number}: {exc}", kind="notice"))
            continue
        if not elements:
            failed = True  # not cached, so a transient empty answer is retried on the next ingest
            sections.append(_section(box_file, "Notice", f"Parse returned no content for {name} page {page_number}", kind="notice"))
            continue
        sections.extend(elements_to_sections(elements, box_file, page_number))
    if total > len(pages):
        sections.append(_section(box_file, "Notice", f"Parsed first {len(pages)} of {total} pages of {name}", kind="notice"))
    if not failed:
        parse_cache.put(key, [{"heading": s.heading, "text": s.text, "kind": s.kind} for s in sections])
    return sections
