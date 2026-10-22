"""Turn Nemotron Parse 2.0 output into ParsedSections.

The element grammar is the one NVIDIA uses in `postprocessing.py` of the Hugging Face repo
`nvidia/NVIDIA-Nemotron-Parse-2.0`: each element is `<x_..><y_..>TEXT<x_..><y_..><class_NAME>` with
coordinates normalized to 0..1. Tables arrive as LaTeX `tabular` and are converted to markdown here
with a small converter that covers rules, rows, cells and \\multicolumn; anything it cannot read is
kept as the original LaTeX.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from akf_workshop.box_source.schema import BoxFile

from .schema import ParsedSection

ELEMENT_RE = re.compile(
    r"<x_(\d+(?:\.\d+)?)><y_(\d+(?:\.\d+)?)>(.*?)<x_(\d+(?:\.\d+)?)><y_(\d+(?:\.\d+)?)><class_([^>]+)>",
    re.DOTALL,
)
STRAY_TOKENS = ("<tbc>", "\\<|unk|\\>", "<|unk|>", "\\unknown")
HEADING_CLASSES = {"Title", "Section-header"}
DROP_CLASSES = {"Picture", "Chart", "Page-header", "Page-footer", "Footnote"}

TABULAR_RE = re.compile(r"\\begin\{tabular\}\s*(?:\{[^}]*\})?(.*?)\\end\{tabular\}", re.DOTALL)
RULE_RE = re.compile(r"\\(?:hline|toprule|midrule|bottomrule)\b|\\cline\{[^}]*\}")
MULTICOLUMN_RE = re.compile(r"\\multicolumn\{(\d+)\}\{[^}]*\}\{(.*)\}", re.DOTALL)
MULTIROW_RE = re.compile(r"\\multirow\{\d+\}\{[^}]*\}\{(.*)\}", re.DOTALL)


@dataclass(frozen=True)
class Element:
    cls: str
    bbox: tuple[float, float, float, float]
    text: str


def elements_from_response(raw: str) -> list[Element]:
    """Parse the raw Parse 2.0 string into elements; empty or unparseable input gives []."""
    if not raw:
        return []
    elements: list[Element] = []
    for x1, y1, text, x2, y2, cls in ELEMENT_RE.findall(raw):
        clean = text
        for token in STRAY_TOKENS:
            clean = clean.replace(token, "")
        elements.append(Element(cls=cls.strip(), bbox=(float(x1), float(y1), float(x2), float(y2)), text=clean.strip()))
    return elements


def elements_from_v1_response(raw: str) -> list[Element]:
    """Parse the v1 `markdown_bbox` tool arguments: a nested list of {bbox: {xmin, ymin, xmax, ymax}, text, type}."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    while isinstance(data, list) and data and isinstance(data[0], list):
        data = data[0]
    if not isinstance(data, list):
        return []
    elements: list[Element] = []
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get("bbox"), dict):
            continue
        box = item["bbox"]
        try:
            bbox = (float(box["xmin"]), float(box["ymin"]), float(box["xmax"]), float(box["ymax"]))
        except (KeyError, TypeError, ValueError):
            continue
        elements.append(Element(cls=str(item.get("type", "Text")), bbox=bbox, text=str(item.get("text", "")).strip()))
    return elements


def latex_table_to_markdown(text: str) -> str:
    """Convert a LaTeX tabular to a markdown table; return the input unchanged if that fails."""
    match = TABULAR_RE.search(text)
    if not match:
        return text
    try:
        body = RULE_RE.sub("", match.group(1))
        rows: list[list[str]] = []
        for raw_row in re.split(r"\\\\", body):
            if not raw_row.strip():
                continue
            cells: list[str] = []
            for raw_cell in raw_row.split("&"):
                cell = raw_cell.strip()
                span = 1
                multi = MULTICOLUMN_RE.fullmatch(cell)
                if multi:
                    span = int(multi.group(1))
                    cell = multi.group(2).strip()
                cells.append(_clean_cell(cell))
                cells.extend([""] * (span - 1))
            rows.append(cells)
        if not rows:
            return text
        width = max(len(row) for row in rows)
        rows = [row + [""] * (width - len(row)) for row in rows]
        lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
        lines.extend("| " + " | ".join(row) + " |" for row in rows[1:])
        return "\n".join(lines)
    except Exception:  # noqa: BLE001 - a table we cannot read is kept as LaTeX, never lost
        return text


def _clean_cell(cell: str) -> str:
    cell = MULTIROW_RE.sub(r"\1", cell)
    cell = re.sub(r"\\textbf\{([^}]*)\}", r"**\1**", cell)
    cell = re.sub(r"\\textit\{([^}]*)\}", r"*\1*", cell)
    for escaped, plain in (("\\&", "&"), ("\\%", "%"), ("\\_", "_"), ("\\#", "#"), ("\\$", "$")):
        cell = cell.replace(escaped, plain)
    return " ".join(cell.replace("|", "\\|").split())


def elements_to_sections(elements: list[Element], box_file: BoxFile, page: int) -> list[ParsedSection]:
    """Group elements into sections: headings open a section, tables stand alone, figures are dropped."""
    sections: list[ParsedSection] = []
    heading = f"p{page}: {box_file.name}"
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            sections.append(_section(box_file, heading, "\n".join(buffer).strip(), "text"))
            buffer.clear()

    for element in elements:
        if element.cls in HEADING_CLASSES:
            flush()
            heading = f"p{page}: {element.text.lstrip('#').strip() or box_file.name}"  # a Title arrives as markdown "# ..."
        elif element.cls == "Table":
            flush()
            sections.append(_section(box_file, heading, latex_table_to_markdown(element.text), "table"))
        elif element.cls in DROP_CLASSES:
            continue
        else:
            lines = [line.strip() for line in element.text.replace("<br>", "\n").split("\n") if line.strip()]
            if lines:
                buffer.append("\n".join(lines))
    flush()
    return sections


def _section(box_file: BoxFile, heading: str, text: str, kind: str) -> ParsedSection:
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
