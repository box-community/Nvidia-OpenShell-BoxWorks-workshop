"""A tool-calling agent driven by hosted Nemotron 3.5 Super.

The model decides which tools to call and writes the answer. The code keeps control of what the
model can see: every tool runs with the asker's identity, so permissions are enforced in code, and a
search the reranker scores below the threshold returns no passages, so there is nothing to invent from.
If the model call fails, the rule-based `AgentHarness` answers instead and the trace says so.

With a workspace (see workspace.py) the agent also gets file tools. In an OpenShell sandbox those run
inside the sandbox, where Box Mount syncs them to Box and OpenShell's network policy governs what
reaches Box. The tools report only the local result: whether Box accepted a change is checked in Box.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from akf_workshop.nvidia_clients import DEFAULT_CHAT_MODEL, chat_remote, remote_enabled

from .harness import AgentHarness
from .trace import Trace
from .workspace import WorkspaceError

MAX_TURNS = 6
RATE_LIMIT_WAITS = (5, 10, 20)  # seconds to wait after each HTTP 429 before trying again
ERROR_RETRY_WAITS = (3, 8)  # seconds to wait after a server error or timeout before trying again
CHUNK_ID_RE = re.compile(r"\[(box-[0-9a-f]+:\d{4})\]")

SYSTEM_PROMPT = """You are a support knowledge agent. You may only use information returned by your tools.
- For questions about policies, documents or how something works, call search_documents first.
- For questions about which account is at risk, call predict_support_risk. If the user also asks what to do, search the policy too.
- Cite every factual claim with the chunk ID in square brackets, for example [box-842709b6535d:0002].
- If a tool returns status insufficient_context or denied, or no passages, say you could not find enough permitted context. Do not guess.
- Keep the answer short: two to four sentences."""

WORKSPACE_PROMPT = """
You can also work with files in the user's Box workspace with the workspace tools.
- Paths are relative to the workspace, for example Reviewed/report.md.
- Write only the files the user asks for. Never overwrite; if a file exists, stop and say so.
- Delete only a file the user names explicitly, and nothing else. Never try another way to delete.
- These tools act on the local working copy. Box Mount syncs it with Box, and policy may block some
  changes from reaching Box. Report the local result, and do not claim anything about Box without evidence."""

WORKSPACE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_workspace",
            "description": "List the files in the Box workspace (the local working copy that Box Mount syncs).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_workspace_file",
            "description": "Read a text file from the Box workspace.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_workspace_file",
            "description": "Create a new text file in the Box workspace. Fails if the file already exists.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_workspace_file",
            "description": "Delete one file from the local Box workspace. Box Mount then asks Box to delete it, which policy may block.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        },
    },
]
WORKSPACE_TOOL_NAMES = {tool["function"]["name"] for tool in WORKSPACE_TOOLS}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "Search the Box documents the current user is allowed to see. Returns the best passages with their chunk IDs.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What to search for, in plain words."}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "predict_support_risk",
            "description": "Predict which customer account has the highest support risk, from the account and support-case tables.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


class NemotronAgent:
    def __init__(self, sample_box_root: Path, workspace=None):
        self.harness = AgentHarness(sample_box_root)
        self.workspace = workspace
        self.tools = TOOLS + (WORKSPACE_TOOLS if workspace else [])
        self.system_prompt = SYSTEM_PROMPT + (WORKSPACE_PROMPT if workspace else "")

    def ingest(self) -> dict:
        return self.harness.ingest()

    def ask(self, query: str, user: str, groups: set[str]) -> dict[str, Any]:
        if not remote_enabled():
            raise RuntimeError("The Nemotron agent needs remote mode: set NVIDIA_API_KEY and NVIDIA_USE_REMOTE=1")
        trace = Trace()
        model = _model_name()
        trace.add(
            "plan", agent="nemotron", model=model, tools=[tool["function"]["name"] for tool in self.tools],
            workspace=self.workspace.label if self.workspace else None,
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": query}]
        retrieved: dict[str, dict] = {}
        tool_statuses: list[str] = []
        skill_evidence: list[dict] = []
        answer = ""
        for turn in range(1, MAX_TURNS + 1):
            last_turn = turn == MAX_TURNS
            try:
                message = self._chat(messages, None if last_turn else self.tools, trace, turn)
            except (RuntimeError, ValueError, OSError) as exc:
                return self._fallback(query, user, groups, trace, exc)
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                answer = (message.get("content") or "").strip()
                break
            messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls})
            for call in tool_calls:
                name = call.get("function", {}).get("name", "")
                arguments = _arguments(call.get("function", {}).get("arguments"))
                start = time.perf_counter()
                result = self._run_tool(name, arguments, user, groups, retrieved, skill_evidence)
                tool_statuses.append(f"{name}:{result.get('status', 'error')}")
                shown = {key: (f"<{len(value)} characters>" if key == "content" else value) for key, value in arguments.items()}
                trace.add("tool", tool=name, arguments=shown, status=result.get("status"), result=result.get("message"), trace_ms=round((time.perf_counter() - start) * 1000, 2))
                messages.append({"role": "tool", "tool_call_id": call.get("id", name), "content": json.dumps(result)})

        cited_ids = list(dict.fromkeys(CHUNK_ID_RE.findall(answer)))
        unknown = [chunk_id for chunk_id in cited_ids if chunk_id not in retrieved]
        # Only passages the answer actually cites count as evidence; an answer that cites nothing is not grounded.
        citations = [retrieved[chunk_id] for chunk_id in cited_ids if chunk_id in retrieved]
        acted = any(status.split(":")[0] in WORKSPACE_TOOL_NAMES and status.endswith(":ok") for status in tool_statuses)
        status = _status(tool_statuses, bool(citations), "predict_support_risk:ok" in tool_statuses or acted)
        trace.add("final", status=status, cited=len(citations), unknown_citations=unknown)
        return {
            "answer": answer,
            "citations": citations,
            "skill_evidence": skill_evidence,
            "status": status,
            "agent": "nemotron",
            "model": model,
            "trace": trace.as_dict(),
        }

    def _chat(self, messages: list[dict], tools: list[dict] | None, trace: Trace, turn: int) -> dict:
        """Call the model, waiting and retrying on rate limits (429) and on transient server errors or timeouts."""
        start = time.perf_counter()
        rate_waits = list(RATE_LIMIT_WAITS)
        error_waits = list(ERROR_RETRY_WAITS)
        while True:
            try:
                message = chat_remote(messages, tools=tools)
                break
            except (RuntimeError, ValueError, OSError) as error:
                rate_limited = "error 429" in str(error)
                waits = rate_waits if rate_limited else error_waits
                if not waits:
                    raise
                wait = waits.pop(0)
                trace.add("llm_rate_limited" if rate_limited else "llm_retry", turn=turn, wait_seconds=wait, error=str(error)[:200])
                time.sleep(wait)
        calls = [call.get("function", {}).get("name") for call in message.get("tool_calls") or []]
        trace.add("llm_call", turn=turn, tool_calls=calls, trace_ms=round((time.perf_counter() - start) * 1000, 2))
        return message

    def _run_tool(self, name: str, arguments: dict, user: str, groups: set[str], retrieved: dict, skill_evidence: list) -> dict:
        if name == "search_documents":
            query = str(arguments.get("query") or "").strip()
            if not query:
                return {"status": "error", "message": "query is required"}
            result = self.harness.pipeline.retrieve(query, user=user, groups=groups)
            if result["status"] != "ok":
                return {"status": "insufficient_context", "passages": []}
            passages = []
            for citation, ranked in zip(result["citations"], result["results"]):
                retrieved[citation["chunk_id"]] = citation
                passages.append({"chunk_id": citation["chunk_id"], "file": citation["name"], "text": ranked.chunk.text})
            return {"status": "ok", "passages": passages}
        if name == "predict_support_risk":
            result = self.harness.registry.call("kumo_prediction", query="predict support risk", user=user, groups=groups)
            if result["status"] == "ok":
                skill_evidence.extend(result.get("evidence", []))
            return {"status": result["status"], "summary": result["answer"], "evidence": json.dumps(result.get("evidence", []))[:1500]}
        if name in WORKSPACE_TOOL_NAMES and self.workspace:
            return self._run_workspace_tool(name, arguments)
        return {"status": "error", "message": f"unknown tool {name}"}

    def _run_workspace_tool(self, name: str, arguments: dict) -> dict:
        path = str(arguments.get("path") or "")
        try:
            if name == "list_workspace":
                return {"status": "ok", "files": self.workspace.list()[:200]}
            if name == "read_workspace_file":
                return {"status": "ok", "path": path, "content": self.workspace.read(path)}
            if name == "write_workspace_file":
                self.workspace.write(path, str(arguments.get("content") or ""))
                return {"status": "ok", "path": path, "message": "Written to the local workspace. Box Mount uploads it to Box; delivery is not verified by this tool."}
            if name == "delete_workspace_file":
                self.workspace.delete(path)
                return {"status": "ok", "path": path, "message": "Deleted from the local workspace. Box Mount will ask Box to delete it too, and policy may block that. The Box result is not known to this tool."}
        except WorkspaceError as exc:
            return {"status": "error", "path": path, "message": str(exc)}
        return {"status": "error", "message": f"unknown tool {name}"}

    def _fallback(self, query: str, user: str, groups: set[str], trace: Trace, error: Exception) -> dict[str, Any]:
        if self.workspace:
            # File actions may already have happened, so don't hand over to an agent that can't report them.
            trace.add("llm_failed", error=str(error)[:200], fallback=None)
            return {
                "answer": "The model stopped responding before the task finished. Check the trace for any file actions already taken.",
                "citations": [], "skill_evidence": [], "status": "error", "agent": "nemotron", "model": _model_name(),
                "trace": trace.as_dict(),
            }
        trace.add("llm_failed", error=str(error)[:200], fallback="rule-based agent")
        response = self.harness.ask(query, user=user, groups=groups)
        response["agent"] = "rule-based-fallback"
        response["model"] = None
        response["trace"]["events"] = trace.events + response["trace"]["events"]
        return response


def _model_name() -> str:
    return os.getenv("NVIDIA_CHAT_MODEL", DEFAULT_CHAT_MODEL)


def _arguments(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _status(tool_statuses: list[str], has_citations: bool, prediction_ok: bool) -> str:
    """ok only when the answer is backed by a cited passage or a successful prediction."""
    if has_citations or prediction_ok:
        return "ok"
    if not tool_statuses:
        return "ungrounded"  # the model answered without calling any tool
    if all(status.endswith(":denied") for status in tool_statuses):
        return "denied"
    return "insufficient_context"
