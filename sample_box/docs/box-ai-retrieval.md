# Box AI Retrieval Evaluation

Box wants enterprise agents to move beyond keyword file search into permission-aware context retrieval.

The retrieval lane uses four stages:

1. Parse files into structured text and layout.
2. Embed passages and queries.
3. Search candidate chunks with a vector index.
4. Rerank candidates against the actual question before building cited context.

The workshop evaluates retrieval with Recall@k, MRR@k, nDCG@k, citation coverage, and insufficient-context behavior.

## Chunking Guidance

Start with heading-aware chunks. Keep source file ID, path, version, labels, and ACL metadata attached to every chunk.

For Box-style enterprise content, chunk size should be treated as a quality and cost knob. Larger chunks can improve answer context, but may increase embedding and reranking cost.

## Citation Contract

Every answer must include the source file name, path, version, and chunk ID. If the system cannot find sufficient context, it should say so instead of inventing an answer.
