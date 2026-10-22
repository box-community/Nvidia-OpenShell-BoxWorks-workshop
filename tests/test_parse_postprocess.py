from __future__ import annotations

import unittest
from pathlib import Path

from akf_workshop.akf_search.parse_postprocess import (
    Element,
    elements_from_response,
    elements_from_v1_response,
    elements_to_sections,
    latex_table_to_markdown,
)
from akf_workshop.box_source.schema import AccessControl, BoxFile

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BB = (0.1, 0.1, 0.5, 0.2)
box_file = BoxFile(file_id="box-test", name="policy.pdf", path="/Box Placeholder/docs/policy.pdf", relative_path="docs/policy.pdf",
                   mime_type="application/pdf", version="v1", owner="o@example.com", modified_at="2026-10-17T00:00:00Z",
                   labels=("docs",), acl=AccessControl(groups=("support-leads",)))


class PostprocessTests(unittest.TestCase):
    def test_fixture_yields_elements_with_text_and_bbox(self) -> None:
        els = elements_from_response(FIXTURES.joinpath("parse2_response.txt").read_text())
        self.assertEqual(len(els), 7)
        self.assertEqual(sorted({e.cls for e in els}), ["Section-header", "Text"])
        self.assertTrue(all(len(e.bbox) == 4 and all(0.0 <= v <= 1.0 for v in e.bbox) for e in els))
        self.assertIn("escalated", " ".join(e.text for e in els).lower())

    def test_v1_fixture_yields_elements(self) -> None:
        els = elements_from_v1_response(FIXTURES.joinpath("parse1_response.json").read_text())
        self.assertEqual(len(els), 9)
        self.assertEqual(els[0].cls, "Section-header")
        self.assertEqual(els[0].text, "Enterprise Support Policy")
        self.assertTrue(all(len(e.bbox) == 4 and all(0.0 <= v <= 1.0 for v in e.bbox) for e in els))

    def test_v1_garbage_yields_empty(self) -> None:
        for raw in ("", "not json", "[]", "[[]]", "{}", '[[{"text": "no bbox"}]]'):
            self.assertEqual(elements_from_v1_response(raw), [], raw)

    def test_garbage_yields_empty(self) -> None:
        self.assertEqual(elements_from_response(""), [])
        self.assertEqual(elements_from_response("<x_0.1>"), [])
        self.assertEqual(elements_from_response("plain words with no tags"), [])

    def test_stray_tokens_are_stripped(self) -> None:
        raw = "<x_0.1><y_0.1>Hello<tbc> world<|unk|><x_0.5><y_0.2><class_Text>"
        self.assertEqual(elements_from_response(raw)[0].text, "Hello world")

    def test_latex_table_to_markdown(self) -> None:
        latex = r"\begin{tabular}{cc} \hline **Priority** & Target \\ \hline P1 & 15 min \\ P2 & 2 hours \\ \hline \end{tabular}"
        md = latex_table_to_markdown(latex)
        self.assertEqual(md.splitlines()[0], "| **Priority** | Target |")
        self.assertEqual(md.splitlines()[1], "|---|---|")
        self.assertIn("| P1 | 15 min |", md)
        self.assertIn("| P2 | 2 hours |", md)

    def test_table_conversion_falls_back_to_input(self) -> None:
        self.assertEqual(latex_table_to_markdown("not a table at all"), "not a table at all")

    def test_table_is_converted_and_kept_as_own_section(self) -> None:
        latex = r"\begin{tabular}{cc} Priority & Target \\ P1 & 15 min \\ \end{tabular}"
        els = [Element("Section-header", BB, "Response targets"), Element("Text", BB, "Targets below."), Element("Table", BB, latex)]
        secs = elements_to_sections(els, box_file, page=1)
        self.assertEqual([s.kind for s in secs], ["text", "table"])
        self.assertTrue(secs[0].heading.startswith("p1:"))
        self.assertIn("| P1 | 15 min |", secs[1].text)

    def test_unknown_class_appends_as_text_and_pictures_drop(self) -> None:
        els = [Element("Title", BB, "T"), Element("Bibliography", BB, "ref 1"), Element("Chart", BB, "ignored"), Element("Picture", BB, "also ignored")]
        secs = elements_to_sections(els, box_file, page=2)
        self.assertEqual(len(secs), 1)
        self.assertEqual(secs[0].heading, "p2: T")
        self.assertIn("ref 1", secs[0].text)
        self.assertNotIn("ignored", secs[0].text)

    def test_markdown_heading_marker_is_stripped(self) -> None:
        secs = elements_to_sections([Element("Title", BB, "# Support Response Targets"), Element("Text", BB, "body")], box_file, page=1)
        self.assertEqual(secs[0].heading, "p1: Support Response Targets")

    def test_sections_carry_box_metadata_and_br_becomes_newline(self) -> None:
        els = [Element("Text", BB, "line one<br> line two")]
        secs = elements_to_sections(els, box_file, page=1)
        self.assertEqual(secs[0].acl, box_file.acl)
        self.assertEqual(secs[0].source_version, "v1")
        self.assertIn("line one\nline two", secs[0].text)


if __name__ == "__main__":
    unittest.main()
