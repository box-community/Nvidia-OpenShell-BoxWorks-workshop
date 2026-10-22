from __future__ import annotations

import unittest

from akf_workshop.akf_search.chunk import chunk_sections
from akf_workshop.akf_search.schema import ParsedSection
from akf_workshop.box_source.schema import AccessControl

COMMON = dict(source_name="x.md", source_path="/x.md", source_version="v1", labels=(), acl=AccessControl())


class ChunkTablesTests(unittest.TestCase):
    def test_table_section_is_one_chunk(self) -> None:
        table = ParsedSection(file_id="f", heading="p1: SLA", text=" ".join(["| a | b |"] * 200), kind="table", **COMMON)
        chunks = chunk_sections([table])
        self.assertEqual(len(chunks), 1)
        self.assertTrue(chunks[0].text.startswith("p1: SLA\n"))
        self.assertEqual(chunks[0].text.count("| a | b |"), 200)

    def test_text_section_still_splits(self) -> None:
        text = ParsedSection(file_id="f", heading="H", text=" ".join(f"w{i}" for i in range(300)), **COMMON)
        self.assertEqual(len(chunk_sections([text])), 3)

    def test_notice_section_yields_no_chunk(self) -> None:
        notice = ParsedSection(file_id="f", heading="Notice", text="PDF not parsed", kind="notice", **COMMON)
        self.assertEqual(chunk_sections([notice]), [])


if __name__ == "__main__":
    unittest.main()
