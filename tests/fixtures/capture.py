"""Capture live NVIDIA responses as offline test fixtures.

Run from the repo root with remote mode on:
    set -a; source .env; set +a; PYTHONPATH=src python3 tests/fixtures/capture.py

Makes three hosted calls (rerank, Nemotron Parse 2.0, Nemotron Parse v1) and writes:
    one_page.pdf, rerank_response.json, parse2_response.txt, parse1_response.json
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

QUERY = "When should enterprise incidents be escalated?"
PASSAGES = [
    "The catalog lists HX-4410 with a two-year warranty.",
    "Enterprise incidents with customer impact should be escalated to the support lead within 30 minutes.",
    "Chunk size should be treated as a quality and cost knob.",
]
PDF_LINES = [
    (20, 740, "Enterprise Support Policy"),
    (12, 710, "This document is restricted to support leads."),
    (16, 680, "Escalation"),
    (12, 660, "Enterprise incidents with customer impact should be escalated to the support lead"),
    (12, 645, "within 30 minutes."),
    (12, 620, "If a customer has more than three open priority cases or an unresolved case older than"),
    (12, 605, "14 days, the account should be marked as elevated risk for the weekly support review."),
    (16, 570, "Response Targets"),
    (12, 550, "Priority 1 cases require an initial response within 15 minutes."),
    (12, 535, "Priority 2 cases require an initial response within 2 hours."),
    (12, 520, "Priority 3 cases require an initial response within 1 business day."),
]
PARSE2_PROMPT = "</s><s><predict_bbox><predict_classes><output_markdown><predict_text_in_pic>"  # hosted docs example
DEFAULT_RERANK_URL = "https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-nemotron-rerank-vl-1b-v2/reranking"
DEFAULT_RERANK_MODEL = "nvidia/llama-nemotron-rerank-vl-1b-v2"


def minimal_pdf(lines: list[tuple[int, int, str]]) -> bytes:
    """A valid single-page PDF with Helvetica text, built by hand so no library is needed."""
    content = "".join(f"BT /F1 {size} Tf 72 {y} Td ({text}) Tj ET\n" for size, y, text in lines).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def render_page_jpeg(pdf_bytes: bytes, scale: float = 2.0, quality: int = 85) -> bytes:
    import pypdfium2  # noqa: WPS433 (lazy on purpose)

    doc = pypdfium2.PdfDocument(pdf_bytes)
    image = doc[0].render(scale=scale).to_pil().convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def main() -> int:
    from akf_workshop import nvidia_clients as nc

    if not nc.remote_enabled():
        print("Set NVIDIA_USE_REMOTE=1 and NVIDIA_API_KEY before capturing fixtures.")
        return 2
    try:
        import pypdfium2  # noqa: F401
        import PIL  # noqa: F401
    except ImportError as exc:
        print(f"pypdfium2 and Pillow are required to render the page: {exc}")
        return 2

    pdf = minimal_pdf(PDF_LINES)
    (HERE / "one_page.pdf").write_bytes(pdf)
    jpeg = render_page_jpeg(pdf)
    data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
    print(f"one_page.pdf written ({len(pdf)} bytes); page image {len(jpeg)} bytes")

    rerank = nc._post_json(
        os.getenv("NVIDIA_RERANK_URL", DEFAULT_RERANK_URL),
        {
            "model": os.getenv("NVIDIA_RERANK_MODEL", DEFAULT_RERANK_MODEL),
            "query": {"text": QUERY},
            "passages": [{"text": p} for p in PASSAGES],
            "truncate": "END",
        },
    )
    (HERE / "rerank_response.json").write_text(json.dumps(rerank, indent=2) + "\n")
    print("rerank rankings:", rerank.get("rankings"))

    parse_url = os.getenv("NVIDIA_PARSE_URL", "https://integrate.api.nvidia.com/v1/chat/completions")
    parse2 = nc._post_json(
        parse_url,
        {
            "model": "nvidia/nemotron-parse-2.0",
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": PARSE2_PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}],
            "max_tokens": 2000,
            "temperature": 0,
        },
    )
    content2 = parse2["choices"][0]["message"]["content"] if "choices" in parse2 else json.dumps(parse2)
    (HERE / "parse2_response.txt").write_text(content2)
    print(f"parse 2.0: {len(content2)} chars; has <x_: {'<x_' in content2}; has <class_: {'<class_' in content2}")

    parse1 = nc._post_json(
        parse_url,
        {
            "model": "nvidia/nemotron-parse",
            "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": data_url}}]}],
            "tools": [{"type": "function", "function": {"name": "markdown_bbox"}}],
            "max_tokens": 3000,
        },
    )
    message = parse1["choices"][0]["message"] if "choices" in parse1 else {}
    tool_calls = message.get("tool_calls") or []
    arguments = tool_calls[0]["function"]["arguments"] if tool_calls else json.dumps(parse1)
    (HERE / "parse1_response.json").write_text(arguments)
    print(f"parse v1: {len(arguments)} chars of tool arguments")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
