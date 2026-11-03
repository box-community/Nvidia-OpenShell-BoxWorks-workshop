"""Rebuild the steps in README.md from docs/workshop-walkthrough.html, so the two never drift apart.

    python3 tools/build_readme.py

Only the part of README.md between the <!-- steps:start --> and <!-- steps:end --> markers is replaced.
The header above and the Reference section below are kept as they are; edit those in README.md directly.
"""
from __future__ import annotations

import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "workshop-walkthrough.html"
README = ROOT / "README.md"
START, END = "<!-- steps:start -->", "<!-- steps:end -->"
VOID = {"meta", "link", "br", "img", "input", "hr"}


class Node:
    def __init__(self, tag, attrs, parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    @property
    def cls(self):
        return set((self.attrs.get("class") or "").split())


class Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", [])
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_endtag(self, tag):
        node = self.cur
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.cur = node.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def find_all(node, pred):
    out = []
    for child in node.children:
        if isinstance(child, Node):
            if pred(child):
                out.append(child)
            out.extend(find_all(child, pred))
    return out


def raw_text(node):
    return "".join(c if isinstance(c, str) else raw_text(c) for c in node.children)


def inline(node):
    parts = []
    for c in node.children:
        if isinstance(c, str):
            if not c:
                continue
            core = " ".join(c.split())
            lead = " " if c[:1].isspace() else ""
            trail = " " if c[-1:].isspace() and core else ""
            parts.append(lead + core + trail if core else " ")
            continue
        if c.tag == "button":
            continue
        inner = inline(c)
        if c.tag == "code":
            parts.append(f"`{raw_text(c).strip()}`")
        elif c.tag == "strong":
            parts.append(f"**{inner.strip()}**")
        elif c.tag == "em":
            parts.append(f"*{inner.strip()}*")
        elif c.tag == "a":
            parts.append(f"[{inner.strip()}]({c.attrs.get('href', '')})")
        elif c.tag == "br":
            parts.append("  \n")
        else:
            parts.append(inner)
    lines = [" ".join(line.split()) for line in "".join(parts).split("  \n")]
    return "  \n".join(lines).strip()


def wrap(node):
    wrapper = Node("wrap", [])
    wrapper.children.append(node)
    return wrapper


def render(node, out):
    def emit(text=""):
        out.extend(line.rstrip() for line in text.split("\n"))

    for c in node.children:
        if isinstance(c, str):
            continue
        tag, cls = c.tag, c.cls
        if tag in ("nav", "button", "label", "script", "style"):
            continue
        if tag == "div" and "step-head" in cls:
            number = find_all(c, lambda n: "step-no" in n.cls)[0]
            title = find_all(c, lambda n: "title" in n.cls)[0]
            emit(f"## {inline(number)}: {inline(title)}")
            emit()
        elif tag == "div" and "term" in cls:
            pre = find_all(c, lambda n: n.tag == "pre")[0]
            label = next((x for x in c.children if isinstance(x, Node) and "label" in x.cls), None)
            label_text = inline(label) if label else ""
            if label_text:
                emit(f"*{label_text}:*")
                emit()
            emit("```" + ("text" if "out" in cls else "bash"))
            emit(raw_text(pre).rstrip("\n"))
            emit("```")
            emit()
        elif tag == "div" and "concept" in cls:
            emit("**Concepts**")
            emit()
            for dt, dd in zip(find_all(c, lambda n: n.tag == "dt"), find_all(c, lambda n: n.tag == "dd")):
                emit(f"- **{inline(dt)}**: {inline(dd)}")
            emit()
        elif tag == "div" and "note" in cls:
            buffer = Node("p", [])

            def flush():
                if buffer.children:
                    text = inline(buffer)
                    if text:
                        out.extend(f"> {line}".rstrip() for line in text.split("\n"))
                        out.append(">")
                    buffer.children.clear()

            for part in c.children:
                if isinstance(part, Node) and part.tag == "div":
                    flush()
                    nested: list[str] = []
                    render(wrap(part), nested)
                    out.extend(f"> {line}".rstrip() for line in nested)
                else:
                    buffer.children.append(part)
            flush()
            while out and out[-1] == ">":
                out.pop()
            out.append("")
        elif tag == "div" and "pipeline" in cls:
            emit(" → ".join(inline(s) for s in c.children if isinstance(s, Node) and s.tag == "span"))
            emit()
        elif tag == "div" and ("legend" in cls or "kicker" in cls):
            continue
        elif tag == "table":
            head = [inline(th) for th in find_all(c, lambda n: n.tag == "th")]
            rows = [[inline(td).replace("|", "\\|") for td in find_all(tr, lambda n: n.tag == "td")]
                    for tr in find_all(c, lambda n: n.tag == "tr") if find_all(tr, lambda n: n.tag == "td")]
            if not any(head) and rows and all(r and r[0].isdigit() for r in rows):
                for r in rows:  # a numbered sequence laid out as a table
                    emit(f"{r[0]}. " + " ".join(cell for cell in r[1:] if cell))
                emit()
                continue
            width = max([len(head)] + [len(r) for r in rows])
            head = head or [""] * width
            emit("| " + " | ".join(head + [""] * (width - len(head))) + " |")
            emit("|" + "---|" * width)
            for r in rows:
                emit("| " + " | ".join(r + [""] * (width - len(r))) + " |")
            emit()
        elif tag == "figure":
            img = find_all(c, lambda n: n.tag == "img")[0]
            alt = " ".join(img.attrs.get("alt", "").split())
            emit(f"![{alt}](docs/{img.attrs.get('src', '')})")
            emit()
            caption = find_all(c, lambda n: n.tag == "figcaption")
            if caption:
                emit(f"*{inline(caption[0])}*")
                emit()
        elif tag in ("ul", "ol"):
            for li in [n for n in c.children if isinstance(n, Node) and n.tag == "li"]:
                emit(f"- {inline(li)}")
            emit()
        elif tag == "h1":
            continue  # the README has its own title
        elif tag == "h4":
            emit(f"### {inline(c)}")
            emit()
        elif tag == "p":
            emit(inline(c))
            emit()
        elif tag in ("section", "header", "main", "div"):
            render(c, out)


def steps_markdown() -> str:
    builder = Builder()
    builder.feed(PAGE.read_text(encoding="utf-8"))
    root = builder.root
    first_step_of_phase = {}
    phase = None
    for li in find_all(root, lambda n: n.tag == "li"):
        if "phase" in li.cls:
            phase = inline(li)
        elif li.attrs.get("data-step") and phase and phase not in first_step_of_phase.values():
            first_step_of_phase[li.attrs["data-step"]] = phase
    main = find_all(root, lambda n: n.tag == "main")[0]
    out: list[str] = []
    for child in main.children:
        if not isinstance(child, Node) or child.tag == "footer":
            continue
        if child.tag == "section" and child.attrs.get("id") in first_step_of_phase:
            out += [f"# {first_step_of_phase[child.attrs['id']]}", ""]
        render(wrap(child), out)
        out += ["---", ""]
    text = "\n".join(out)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip().removesuffix("---").strip()


def main() -> int:
    readme = README.read_text(encoding="utf-8")
    if START not in readme or END not in readme:
        print(f"README.md needs the {START} and {END} markers around the steps.", file=sys.stderr)
        return 1
    before, rest = readme.split(START, 1)
    _, after = rest.split(END, 1)
    README.write_text(f"{before}{START}\n\n{steps_markdown()}\n\n{END}{after}", encoding="utf-8")
    print("README.md steps rebuilt from docs/workshop-walkthrough.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
