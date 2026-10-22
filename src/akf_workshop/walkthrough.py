"""Run one stage of the search lane at a time and print what it does.

    PYTHONPATH=src python3 -m akf_workshop.walkthrough files
    PYTHONPATH=src python3 -m akf_workshop.walkthrough parse
    PYTHONPATH=src python3 -m akf_workshop.walkthrough chunk
    PYTHONPATH=src python3 -m akf_workshop.walkthrough embed
    PYTHONPATH=src python3 -m akf_workshop.walkthrough search "your question"
    PYTHONPATH=src python3 -m akf_workshop.walkthrough rerank "your question"
    PYTHONPATH=src python3 -m akf_workshop.walkthrough answer "your question"

Each subcommand calls the same functions the agent uses, so what you see here is what the agent does.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from akf_workshop.akf_search.chunk import chunk_sections
from akf_workshop.akf_search.embed import embed_texts
from akf_workshop.akf_search.index import cosine
from akf_workshop.akf_search.parse import parse_artifact
from akf_workshop.akf_search.pipeline import SearchPipeline
from akf_workshop.akf_search.rerank import rerank
from akf_workshop.box_source.adapter import BoxPlaceholderAdapter
from akf_workshop.box_source.source import describe_source, make_adapter
from akf_workshop.nvidia_clients import remote_enabled

DEFAULT_QUESTION = "How should the workshop evaluate retrieval quality?"
DEFAULT_EMBED_TEXTS = [
    "How fast must a priority one ticket get a first reply?",
    "Priority 1 cases require an initial response within 15 minutes.",
    "The warranty on the HX-9000 curing light is two years.",
]


def _mode() -> str:
    if remote_enabled():
        return "REMOTE (hosted NVIDIA models are used where available)"
    return "OFFLINE (local fallbacks; no network)"


def _heading(title: str, args: argparse.Namespace) -> None:
    print(f"\n== {title}")
    print(f"   mode: {_mode()}")
    print(f"   user: {args.user}  groups: {sorted(_groups(args))}\n")


def _groups(args: argparse.Namespace) -> set[str]:
    return {group.strip() for group in args.groups.split(",") if group.strip()}


def _first_line(text: str) -> str:
    return text.split("\n", 1)[0]


def _acl_text(acl) -> str:
    parts = [f"user {user}" for user in acl.users] + [f"group {group}" for group in acl.groups]
    return ", ".join(parts) or "nobody"


def step_files(args: argparse.Namespace) -> None:
    """Stage 1: the Box adapter lists files with identity, version, labels and who may see them."""
    _heading("files: adapter.list_files()", args)
    adapter = make_adapter(Path(args.sample_box))
    print(f"source: {describe_source(adapter)}\n")
    groups = _groups(args)
    for box_file in adapter.list_files():
        visible = "you can see it" if box_file.acl.allows(args.user, groups) else "hidden from you"
        print(f"{box_file.name}  ({box_file.mime_type})")
        print(f"   file_id: {box_file.file_id}   version: {box_file.version}   labels: {list(box_file.labels)}")
        print(f"   allowed: {_acl_text(box_file.acl)}  ->  {visible}")


def _parsed_sections(args: argparse.Namespace):
    adapter = make_adapter(Path(args.sample_box))
    sections = []
    for listed in adapter.list_files():
        box_file = adapter.get_file(listed.file_id)
        sections.extend(parse_artifact(box_file, local_root=Path(args.sample_box)))
    return sections


def _single_box_file(path: Path):
    adapter = BoxPlaceholderAdapter(path.parent)
    listed = next((item for item in adapter.list_files() if item.name == path.name), None)
    if listed is None:
        raise SystemExit(f"File not found: {path}")
    return adapter.get_file(listed.file_id)


def _parsed_single_file(path: Path):
    """Parse one file from anywhere, for example a PDF that is not in sample_box."""
    return parse_artifact(_single_box_file(path), local_root=path.parent)


# Nemotron Parse 2.0 places each page, shrunk to fit if larger, in the centre of a 1648 x 2048 canvas and
# reports boxes as fractions of that canvas. Measured on the hosted endpoint at two image sizes.
# The older nvidia/nemotron-parse (the fallback) reports boxes as fractions of the image itself.
PARSE_CANVAS = (1648, 2048)
BOX_COLORS = {"Title": "#d62728", "Section-header": "#ff7f0e", "Text": "#1f77b4", "Table": "#2ca02c"}


def _box_to_pixels(bbox: tuple[float, float, float, float], width: int, height: int) -> tuple[float, float, float, float]:
    canvas_w, canvas_h = PARSE_CANVAS
    scale = min(1.0, canvas_w / width, canvas_h / height)
    offset_x, offset_y = (canvas_w - width * scale) / 2, (canvas_h - height * scale) / 2
    x1, y1, x2, y2 = bbox
    return (
        (x1 * canvas_w - offset_x) / scale,
        (y1 * canvas_h - offset_y) / scale,
        (x2 * canvas_w - offset_x) / scale,
        (y2 * canvas_h - offset_y) / scale,
    )


def _show_boxes(path: Path, out: Path) -> None:
    """Send each page to Nemotron Parse and draw the boxes and classes it returns onto the page."""
    if not remote_enabled():
        raise SystemExit("--show needs remote mode: set NVIDIA_API_KEY and NVIDIA_USE_REMOTE=1")
    import io

    from PIL import Image, ImageDraw, ImageFont

    from akf_workshop.akf_search.pages import page_images
    from akf_workshop.akf_search.parse_postprocess import elements_from_response, elements_from_v1_response
    from akf_workshop.nvidia_clients import parse_image_remote, parse_image_remote_v1

    pages = page_images(_single_box_file(path))
    try:
        font = ImageFont.load_default(size=18)
    except TypeError:  # Pillow older than 10.1
        font = ImageFont.load_default()
    print("\nWhat Nemotron Parse found (class, box in pixels):")
    for number, (image_bytes, mime) in enumerate(pages, start=1):
        page = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(page)
        elements, model, errors = [], "nemotron-parse-2.0", []
        try:
            elements = elements_from_response(parse_image_remote(image_bytes, mime=mime))
        except (RuntimeError, ValueError, OSError) as exc:
            errors.append(f"Parse 2.0: {exc}")
        if not elements:  # Parse 2.0 sometimes returns nothing for a page; the pipeline retries with v1 too
            model = "nemotron-parse (fallback)"
            try:
                elements = elements_from_v1_response(parse_image_remote_v1(image_bytes, mime=mime))
            except (RuntimeError, ValueError, OSError) as exc:
                errors.append(f"fallback: {exc}")
        if not elements:
            print(f"  page {number}: no elements returned; nothing to draw.")
            for error in errors:
                print(f"     {error[:200]}")
            print("     The hosted endpoint may be busy. Wait a minute and run the command again.")
            continue
        print(f"  page {number}: {len(elements)} elements from {model}")
        if model != "nemotron-parse-2.0":
            print("     Parse 2.0 returned nothing, so the older model was used. Its boxes can sit a little off on wide images.")
        for element in elements:
            if model.startswith("nemotron-parse-2.0"):
                box = _box_to_pixels(element.bbox, page.width, page.height)
            else:
                x1, y1, x2, y2 = element.bbox
                box = (x1 * page.width, y1 * page.height, x2 * page.width, y2 * page.height)
            color = BOX_COLORS.get(element.cls, "#7f7f7f")
            draw.rectangle((box[0] - 4, box[1] - 4, box[2] + 4, box[3] + 4), outline=color, width=3)
            draw.text((box[0] - 4, max(box[1] - 26, 0)), element.cls, fill=color, font=font)
            print(f"  page {number}  {element.cls:15} {tuple(round(v) for v in box)}")
        target = out if len(pages) == 1 else out.with_name(f"{out.stem}-p{number}{out.suffix}")
        page.save(target)
        print(f"\nSaved {target}. Open it to see the boxes.")


def step_parse(args: argparse.Namespace) -> None:
    """Stage 2: parse turns each file into sections (a heading plus its text)."""
    _heading("parse: parse_artifact(file)", args)
    sections = _parsed_single_file(Path(args.file)) if args.file else _parsed_sections(args)
    for section in sections:
        words = len(section.text.split())
        print(f"{section.source_name:38} [{section.kind}] {words:3} words  heading: {section.heading}")
    print(f"\n{len(sections)} sections. Markdown splits at '#' headings; a CSV becomes one summary section.")
    if any(section.kind == "notice" for section in sections):
        print("A [notice] means the file was skipped. Offline, PDFs and images can't be parsed; use remote mode.")
    if args.file:
        print()
        for section in sections:
            print(f"--- [{section.kind}] {section.heading}\n{section.text[:300]}\n")
    if args.show:
        if not args.file:
            raise SystemExit("--show needs --file")
        _show_boxes(Path(args.file), Path(args.show))


def step_chunk(args: argparse.Namespace) -> None:
    """Stage 3: chunk cuts sections into pieces of at most 120 words, each carrying its file's ACL."""
    _heading("chunk: chunk_sections(sections)", args)
    sections = _parsed_sections(args)
    chunks = chunk_sections(sections)
    for chunk in chunks:
        words = len(chunk.text.split())
        print(f"{chunk.chunk_id}  {words:3} words  {chunk.source_name:36} {_first_line(chunk.text)}")
    print(f"\n{len(sections)} sections -> {len(chunks)} chunks. Each chunk keeps its source file, version, labels and ACL.")


def step_embed(args: argparse.Namespace) -> None:
    """Stage 4: embed turns text into a vector so that similar meanings are close together."""
    _heading("embed: embed_texts(texts)", args)
    texts = args.text or DEFAULT_EMBED_TEXTS
    vectors = embed_texts(texts, input_type="query")
    if remote_enabled():
        print(f"model: {os.getenv('NVIDIA_EMBEDDING_MODEL', 'nvidia/nemotron-3-embed-1b')} (hosted)")
    else:
        print("model: local word-hashing stand-in")
    print(f"{len(vectors)} texts -> {len(vectors)} vectors of {len(vectors[0])} numbers each.\n")
    for text, vector in zip(texts, vectors):
        head = ", ".join(f"{value:+.3f}" for value in vector[:6])
        print(f"  \"{text}\"\n     [{head}, ...]")
    if len(vectors) > 1:
        print("\nSimilarity (cosine; higher means closer in meaning, 1.0 is identical):")
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                print(f"  {cosine(vectors[i], vectors[j]):+.3f}   [{i + 1}] vs [{j + 1}]")
    if not remote_enabled():
        print("\nOffline, vectors come from hashing words, so only shared words make texts similar.")
        print("In remote mode, Nemotron Embed scores the paraphrase pair (texts 1 and 2) far higher: about +0.59.")


def _pipeline(args: argparse.Namespace) -> SearchPipeline:
    pipeline = SearchPipeline(Path(args.sample_box))
    pipeline.ingest()
    return pipeline


def step_search(args: argparse.Namespace) -> None:
    """Stage 5: vector search finds the closest chunks the user is allowed to see."""
    _heading(f'search: index.search("{args.question}")', args)
    pipeline = _pipeline(args)
    groups = _groups(args)
    visible = sum(1 for chunk in pipeline.index.chunks if chunk.acl.allows(args.user, groups))
    print(f"permission filter: {visible} of {len(pipeline.index.chunks)} chunks are visible to you; the rest are never scored.\n")
    results = pipeline.index.search(args.question, user=args.user, groups=groups, top_k=12)
    for rank, result in enumerate(results, start=1):
        print(f"{rank:2}. vector {result.vector_score:+.3f}  {result.chunk.source_name:36} {_first_line(result.chunk.text)}")
    print("\nThis is only closeness of vectors. The reranker (next step) reorders these against the actual question.")


def step_rerank(args: argparse.Namespace) -> None:
    """Stage 6: rerank re-scores the vector candidates against the question and reorders them."""
    _heading(f'rerank: rerank("{args.question}", candidates)', args)
    pipeline = _pipeline(args)
    candidates = pipeline.index.search(args.question, user=args.user, groups=_groups(args), top_k=12)
    print("BEFORE (vector order):")
    for rank, result in enumerate(candidates, start=1):
        print(f"{rank:2}. vector {result.vector_score:+.3f}  {result.chunk.source_name:36} {_first_line(result.chunk.text)}")
    reranked = rerank(args.question, candidates, top_k=4)
    print("\nAFTER (reranked, top 4 kept):")
    for rank, result in enumerate(reranked, start=1):
        print(f"{rank:2}. rerank {result.rerank_score:+.3f} ({result.rerank_source})  {result.chunk.source_name:36} {_first_line(result.chunk.text)}")
    if reranked and reranked[0].rerank_source != "hosted":
        print("\nOffline, the rerank score is the share of the question's words found in the chunk (times 2).")
        print("In remote mode it is a model logit that can be negative; higher is still better.")


def step_answer(args: argparse.Namespace) -> None:
    """Stage 7: context building and the ok / insufficient_context decision."""
    _heading(f'answer: retrieve("{args.question}")', args)
    pipeline = _pipeline(args)
    result = pipeline.retrieve(args.question, user=args.user, groups=_groups(args))
    print(f"status:          {result['status']}")
    print(f"rerank_source:   {result['rerank_source']}")
    print(f"top score:       {result['top_rerank_score']}")
    print(f"gap to 2nd:      {result['rerank_gap']}")
    print("\ncitations:")
    for citation in result["citations"]:
        print(f"  {citation['name']:36} {citation['chunk_id']}  score {citation['score']}")
    print("\ncontext handed to the answer step:\n")
    print(result["context"] or "(nothing: no permitted context)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one stage of the search lane and show what it does")
    parser.add_argument("--sample-box", default="sample_box")
    parser.add_argument("--user", default="dev@example.com")
    parser.add_argument("--groups", default="workshop-attendees", help="Comma-separated group names")
    sub = parser.add_subparsers(dest="step", required=True)

    sub.add_parser("files", help="list files, versions and permissions").set_defaults(run=step_files)
    parse = sub.add_parser("parse", help="split files into sections")
    parse.add_argument("--file", help="parse just this file (for example a PDF) instead of sample_box")
    parse.add_argument("--show", metavar="OUT.png", help="with --file in remote mode: save the page with Parse's boxes drawn on it")
    parse.set_defaults(run=step_parse)
    sub.add_parser("chunk", help="cut sections into chunks").set_defaults(run=step_chunk)
    embed = sub.add_parser("embed", help="turn text into vectors and compare them")
    embed.add_argument("text", nargs="*", help="texts to embed (a demo set is used if omitted)")
    embed.set_defaults(run=step_embed)
    for name, run, help_text in (
        ("search", step_search, "vector search over permitted chunks"),
        ("rerank", step_rerank, "reorder the candidates against the question"),
        ("answer", step_answer, "build context and decide ok / insufficient_context"),
    ):
        stage = sub.add_parser(name, help=help_text)
        stage.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
        stage.set_defaults(run=run)

    args = parser.parse_args()
    args.run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
