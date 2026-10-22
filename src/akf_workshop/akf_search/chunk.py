from __future__ import annotations

from .schema import KnowledgeChunk, ParsedSection


def chunk_sections(sections: list[ParsedSection], max_words: int = 120) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    for section in sections:
        if section.kind == "notice":
            continue
        words = section.text.split()
        if not words:
            continue
        # A table is one retrieval unit however long it is: splitting it would orphan rows from their header.
        pieces = [section.text.strip()] if section.kind == "table" else [
            " ".join(words[start : start + max_words]) for start in range(0, len(words), max_words)
        ]
        for text in pieces:
            chunk_id = f"{section.file_id}:{len(chunks):04d}"
            chunks.append(
                KnowledgeChunk(
                    chunk_id=chunk_id,
                    file_id=section.file_id,
                    text=f"{section.heading}\n{text}",
                    source_name=section.source_name,
                    source_path=section.source_path,
                    source_version=section.source_version,
                    labels=section.labels,
                    acl=section.acl,
                )
            )
    return chunks
