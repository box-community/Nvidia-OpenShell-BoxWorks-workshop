# NVIDIA Endpoint Notes

This repo uses local fallbacks by default, but the interfaces are shaped around the NVIDIA components in the source deck.

## Nemotron Parse 2.0

Use for converting document page images into structured text and layout.

- Model: `nvidia/nemotron-parse-2.0`
- Endpoint: `POST https://integrate.api.nvidia.com/v1/chat/completions`
- Request: content parts in the order text, then one `image_url` (a `data:image/jpeg;base64,...` URI). Prompt: `</s><s><predict_bbox><predict_classes><output_markdown><predict_text_in_pic>`. `max_tokens` 2000 (the model's whole context is 4,096 tokens; 4096 is rejected).
- Response: `message.content` is a string of elements `<x_..><y_..>TEXT<x_..><y_..><class_NAME>` with 0..1 coordinates; tables arrive as LaTeX `tabular`. `akf_search/parse_postprocess.py` turns that into sections (headings open a section, tables stand alone and are converted to markdown, figures are dropped).
- How files reach it: the adapter carries bytes for non-text files; `akf_search/pages.py` renders PDF pages to JPEG under 180 KB with `pypdfium2` (install the `pdf` extra) and passes images through; one call per page, at most `AKF_PARSE_MAX_PAGES` pages. Results are cached under `AKF_CACHE_DIR` (default `.akf_cache/`) by content hash, so repeated `ingest` runs do not re-parse.
- Fallback model: when Parse 2.0 returns no elements for a page (observed: `finish_reason: length` with empty content on some pages), the same image is sent to `nvidia/nemotron-parse` (`NVIDIA_PARSE_FALLBACK_MODEL`) with the `markdown_bbox` tool, whose JSON elements are converted the same way. A page that both models leave empty becomes a notice and is not cached, so the next ingest retries it.
- Local fallback: markdown and CSV are split locally without any call; a PDF or image is skipped with a notice when remote mode is off.

## Nemotron 3 Embed 1B

Use for embedding chunks during indexing and embedding queries during retrieval.

- Model: `nvidia/nemotron-3-embed-1b`
- Endpoint: `POST https://integrate.api.nvidia.com/v1/embeddings`
- Required body fields used here: `model`, `input`, `input_type`, `encoding_format`, and `truncate`.
- Important: use `input_type="passage"` for indexed chunks and `input_type="query"` for user questions.
- Local fallback: deterministic hashing vectors in `src/akf_workshop/akf_search/embed.py`.

## Nemotron Rerank

Use for ordering the vector candidates against the actual question and for deciding refusals.

- Model: `nvidia/nemotron-3.5-rerank-8b` (Nemotron 3.5 Rerank 8B; replaced `llama-nemotron-rerank-vl-1b-v2` on 2026-10-21)
- Endpoint: `POST https://ai.api.nvidia.com/v1/retrieval/nvidia/nemotron-3.5-rerank-8b/reranking`
- Request: `{"model", "query": {"text"}, "passages": [{"text"}, ...], "truncate": "END"}`; text-only passages are fine. Response: `rankings: [{index, logit}]`; the client sorts by logit itself.
- In the lane: `akf_search/rerank.py` sends the 12 vector candidates in one call; the order follows the logit. `status` is `ok` when the top logit is at least `AKF_RERANK_MIN_LOGIT` (default `-3.1`, calibrated on the golden questions: answerable ones scored -2.87 and up, no-answer ones -3.31 and below); the pipeline also reports `top_rerank_score` and `rerank_gap` so the threshold can be recalibrated on real content.
- Local fallback: the term-overlap reranker and the original `score >= 0.3 and rerank >= 0.75` rule; any hosted failure (HTTP error, network error, short response) falls back the same way and marks `rerank_source: "lexical-fallback"`.

## Vector search

Runs locally in pure Python, on any laptop: `akf_search/index.py` (`ExactIndex`) compares the query vector with every chunk the user is allowed to see. The permission mask is applied before the top-k is chosen, so restricted chunks are never scored. Nothing to configure.

## Kumo Relational

Use for prediction over structured, relational data.

- Model: `kumo-relational`
- Hosted endpoint used by this repo: `POST https://ai.api.nvidia.com/v1/structured-data/nvidia/kumo-relational/predictions`
- The request includes `model`, `task`, `schema`, `context`, `predict`, and `output`.
- Local fallback: deterministic support-risk scoring in `src/akf_workshop/akf_skills/kumo.py`.

## Nemotron 3.5 Super (the AI agent)

Use for the tool-calling agent: the model chooses tools and writes a cited answer.

- Model: `nvidia/nemotron-3.5-super-vl-120b-a12b`
- Endpoint: `POST https://integrate.api.nvidia.com/v1/chat/completions` (OpenAI-compatible), with `tools` and `tool_choice: "auto"`, `temperature` 0. The response message has `content`, `tool_calls` and a separate `reasoning_content`.
- In the repo: `nvidia_clients.chat_remote`, used by `agent/nemotron_agent.py`. Run with `agent.cli --agent nemotron`. Up to 4 model turns; one retry per turn; on failure the rule-based agent answers and the output says `"agent": "rule-based-fallback"`.
- Tools: `search_documents(query)` runs the retrieval lane as the asker; `predict_support_risk()` runs the Kumo skill as the asker. Permissions, the rerank threshold and the citation check are enforced in code, not by the model.
- Observed 2026-10-20: 1 to 8 s per turn, with intermittent HTTP 500s and timeouts.
- No local fallback model: without remote mode, `--agent nemotron` exits with a message and the default rule-based agent is used.

## Environment

```bash
export NVIDIA_API_KEY="nvapi-..."
export NVIDIA_USE_REMOTE=1
```

Remote endpoint calls are off unless both variables are set. Optional, with defaults:

| Variable | Default | Meaning |
| --- | --- | --- |
| `NVIDIA_RERANK_URL` | the VL reranker URL above | hosted rerank endpoint |
| `NVIDIA_RERANK_MODEL` | `nvidia/nemotron-3.5-rerank-8b` | rerank model id |
| `NVIDIA_CHAT_MODEL` | `nvidia/nemotron-3.5-super-vl-120b-a12b` | model for `--agent nemotron` |
| `NVIDIA_CHAT_URL` | `https://integrate.api.nvidia.com/v1/chat/completions` | chat endpoint |
| `AKF_RERANK_MIN_LOGIT` | `-3.1` | top rerank logit needed for `status: ok` |
| `NVIDIA_PARSE_FALLBACK_MODEL` | `nvidia/nemotron-parse` | model tried when Parse 2.0 returns no elements for a page |
| `AKF_CACHE_DIR` | `.akf_cache` | parsed-page cache directory |
| `AKF_PARSE_MAX_PAGES` | `20` | pages parsed per PDF |
| `AKF_PARSE_MAX_IMAGE_BYTES` | `180000` | JPEG size cap per page image |
