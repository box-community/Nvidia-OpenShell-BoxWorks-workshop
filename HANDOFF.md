# Handoff: Box + NVIDIA Agent Knowledge Foundation Workshop

## What This Package Is

This is a runnable developer workshop starter for building a Box-backed Agent Knowledge Foundation pattern.

The workshop uses Box as the unstructured file store placeholder and focuses on two lanes:

- Search: Box files -> Parse -> Embed -> vector search -> Rerank -> cited context
- Predict: Kumo-style support-risk prediction over structured sidecar data

It is designed to be Codex-friendly: attendees can ask Codex to inspect, implement, test, and explain each boundary.

## GPU Requirement

No GPU is required for the workshop.

The code runs entirely with local CPU fallbacks by default:

- local files instead of Box API
- markdown/CSV parsing instead of hosted Parse
- deterministic local vectors instead of hosted embeddings
- CPU in-memory vector search
- deterministic prediction instead of hosted Kumo

If NVIDIA hosted endpoints are enabled with an API key, attendees still do not need local GPUs.

## Quick Run

From this folder:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 -m akf_workshop.agent.cli ingest
PYTHONPATH=src python3 -m akf_workshop.agent.cli ask "How should the workshop evaluate retrieval quality?"
PYTHONPATH=src python3 -m akf_workshop.agent.cli --user support-lead@example.com --groups support-leads ask "Predict support risk and cite the policy."
PYTHONPATH=src python3 -m akf_workshop.evals.run_eval
```

## Optional NVIDIA Endpoint Mode

Remote calls are disabled by default. To enable them:

```bash
export NVIDIA_API_KEY="nvapi-..."
export NVIDIA_USE_REMOTE=1
```

Configured endpoints live in `.env.example` and are documented in `docs/nvidia-endpoints.md`.

## Important Files

- `README.md`: the step-by-step workshop guide (the lab flow lives here now)
- `src/akf_workshop/walkthrough.py`: runs one pipeline stage at a time for the guide
- `docs/nvidia-endpoints.md`: endpoint and production swap notes
- `sample_box/`: local Box placeholder files and permissions
- `src/akf_workshop/box_source/adapter.py`: Box adapter boundary
- `src/akf_workshop/akf_search/`: Parse, Embed, vector search, Rerank, Context
- `src/akf_workshop/akf_skills/kumo.py`: local Kumo fallback and remote payload builder
- `src/akf_workshop/agent/harness.py`: agent skill routing and response contract
- `src/akf_workshop/evals/`: golden questions and retrieval metrics

## Workshop Story

The clean story to tell:

1. Box keeps enterprise content, metadata, versions, and permissions.
2. The knowledge foundation prepares content into chunks with preserved ACLs.
3. Retrieval uses embeddings, vector search, rerank, and citations.
4. Prediction uses Kumo-style structured sidecar data.
5. The agent calls retrieval and prediction skills through a stable harness.
6. Evals and traces make quality, refusal behavior, and tool-loop cost visible.

## Known Intentional Simplifications

- Box is represented by local files.
- Vector search is a CPU in-memory index (no GPU library).
- Nemotron Rerank is represented by a lexical reranker.
- Kumo is represented by deterministic local scoring unless remote mode is enabled.
- The answer generator is deliberately simple so the workshop centers on data, retrieval, permissions, evals, and traces rather than prompt engineering.

## Verification Snapshot

Last local verification:

```text
Ran 9 tests: OK
Eval status checks: pass
```

## Next Best Improvements

- Add a real Box adapter when Box credentials are available.
- Replace the local reranker with a hosted rerank model/API when selected.
- Add a browser UI for the workshop demo.
- Add richer sample documents and a larger golden eval set.
- Decide whether insufficient-context responses should hide citations from unauthorized or weakly matched documents.
