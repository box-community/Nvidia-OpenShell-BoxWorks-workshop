from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def remote_enabled() -> bool:
    return os.getenv("NVIDIA_USE_REMOTE", "0") == "1" and bool(os.getenv("NVIDIA_API_KEY"))


def _headers() -> dict[str, str]:
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise RuntimeError("NVIDIA_API_KEY is required when NVIDIA_USE_REMOTE=1")
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"NVIDIA API error {exc.code}: {body}") from exc


def _get_json(url: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"NVIDIA API error {exc.code}: {body}") from exc


def embed_texts_remote(texts: list[str], input_type: str) -> list[list[float]]:
    url = os.getenv("NVIDIA_EMBEDDING_URL", "https://integrate.api.nvidia.com/v1/embeddings")
    model = os.getenv("NVIDIA_EMBEDDING_MODEL", "nvidia/nemotron-3-embed-1b")
    payload = {
        "model": model,
        "input": texts,
        "input_type": input_type,
        "encoding_format": "float",
        "truncate": "END",
    }
    response = _post_json(url, payload)
    return [item["embedding"] for item in response["data"]]


DEFAULT_RERANK_URL = "https://ai.api.nvidia.com/v1/retrieval/nvidia/nemotron-3.5-rerank-8b/reranking"
DEFAULT_RERANK_MODEL = "nvidia/nemotron-3.5-rerank-8b"


def rerank_remote(query: str, passages: list[str]) -> list[tuple[int, float]]:
    """Score passages against the query with the hosted Nemotron reranker.

    Returns (passage_index, logit) pairs sorted by logit descending, one per passage.
    Raises RuntimeError on HTTP errors and ValueError if the response does not cover every passage.
    """
    url = os.getenv("NVIDIA_RERANK_URL", DEFAULT_RERANK_URL)
    model = os.getenv("NVIDIA_RERANK_MODEL", DEFAULT_RERANK_MODEL)
    payload = {
        "model": model,
        "query": {"text": query},
        "passages": [{"text": passage} for passage in passages],
        "truncate": "END",
    }
    response = _post_json(url, payload)
    try:
        rankings = response["rankings"]
        pairs = [(int(item["index"]), float(item["logit"])) for item in rankings]
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"rerank response is not in the expected shape: {exc!r}") from exc
    if len(pairs) < len(passages):
        raise ValueError(f"rerank returned {len(pairs)} rankings for {len(passages)} passages")
    indices = [index for index, _ in pairs]
    if any(index < 0 or index >= len(passages) for index in indices):
        raise ValueError(f"rerank returned an out-of-range passage index in {indices}")
    if len(set(indices)) != len(passages):
        raise ValueError(f"rerank returned duplicate passage indices {indices}")
    return sorted(pairs, key=lambda pair: pair[1], reverse=True)


PARSE2_PROMPT = "</s><s><predict_bbox><predict_classes><output_markdown><predict_text_in_pic>"
MIME_BY_SUFFIX = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def parse_image_remote(image: Path | bytes, prompt: str = PARSE2_PROMPT, mime: str = "image/png") -> str:
    """Send one page image to Nemotron Parse and return the raw response text.

    `image` is either raw bytes (with `mime`) or a path whose suffix sets the mime type. The hosted
    model's whole context is 4,096 tokens, so max_tokens stays well under it.
    """
    url = os.getenv("NVIDIA_PARSE_URL", "https://integrate.api.nvidia.com/v1/chat/completions")
    model = os.getenv("NVIDIA_PARSE_MODEL", "nvidia/nemotron-parse-2.0")
    if isinstance(image, (str, Path)):
        path = Path(image)
        data = path.read_bytes()
        mime = MIME_BY_SUFFIX.get(path.suffix.lower(), mime)
    else:
        data = image
    encoded = base64.b64encode(data).decode("ascii")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                ],
            }
        ],
        "max_tokens": 2000,
        "temperature": 0,
    }
    response = _post_json(url, payload)
    if "choices" in response:
        return response["choices"][0]["message"].get("content") or ""
    request_id = response.get("requestId") or response.get("id")
    if not request_id:
        return json.dumps(response)
    return poll_status(request_id)


def parse_image_remote_v1(image: Path | bytes, mime: str = "image/png") -> str:
    """Fallback parser: `nvidia/nemotron-parse` with its `markdown_bbox` tool.

    Returns the tool call's JSON `arguments` string (a nested list of {bbox, text, type} elements),
    or "" when the model returned no tool call. Used when Parse 2.0 returns no elements for a page.
    """
    url = os.getenv("NVIDIA_PARSE_URL", "https://integrate.api.nvidia.com/v1/chat/completions")
    model = os.getenv("NVIDIA_PARSE_FALLBACK_MODEL", "nvidia/nemotron-parse")
    if isinstance(image, (str, Path)):
        path = Path(image)
        data = path.read_bytes()
        mime = MIME_BY_SUFFIX.get(path.suffix.lower(), mime)
    else:
        data = image
    encoded = base64.b64encode(data).decode("ascii")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}]}],
        "tools": [{"type": "function", "function": {"name": "markdown_bbox"}}],
        "max_tokens": 2000,
    }
    response = _post_json(url, payload)
    choices = response.get("choices") if isinstance(response, dict) else None
    if not choices:
        return ""
    tool_calls = (choices[0].get("message") or {}).get("tool_calls") or []
    if not tool_calls:
        return ""
    return (tool_calls[0].get("function") or {}).get("arguments") or ""


def poll_status(request_id: str, attempts: int = 20, delay_seconds: float = 1.5) -> str:
    base = "https://integrate.api.nvidia.com/v1/status"
    for _ in range(attempts):
        status, response = _get_json(f"{base}/{request_id}")
        if status == 200:
            if "choices" in response:
                return response["choices"][0]["message"]["content"]
            return json.dumps(response)
        time.sleep(delay_seconds)
    raise TimeoutError(f"NVIDIA request {request_id} did not complete")


def kumo_predict_remote(payload: dict[str, Any]) -> dict[str, Any]:
    url = os.getenv("NVIDIA_KUMO_URL", "https://ai.api.nvidia.com/v1/structured-data/nvidia/kumo-relational/predictions")
    return _post_json(url, payload)


DEFAULT_CHAT_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_CHAT_MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"


def chat_remote(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, max_tokens: int = 1000) -> dict[str, Any]:
    """One chat turn with the hosted Nemotron model. Returns the assistant message (content, tool_calls, reasoning_content)."""
    payload: dict[str, Any] = {
        "model": os.getenv("NVIDIA_CHAT_MODEL", DEFAULT_CHAT_MODEL),
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    response = _post_json(os.getenv("NVIDIA_CHAT_URL", DEFAULT_CHAT_URL), payload)
    try:
        return response["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"chat response is not in the expected shape: {exc!r}") from exc
