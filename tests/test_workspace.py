import os as _os

_os.environ.pop("BOX_FOLDER_ID", None)  # these tests use the local sample_box, never live Box

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from akf_workshop.agent import nemotron_agent
from akf_workshop.agent.nemotron_agent import NemotronAgent
from akf_workshop.agent.workspace import LocalWorkspace, SandboxWorkspace, WorkspaceError, clean_path

SAMPLE = Path(__file__).resolve().parents[1] / "sample_box"


class CleanPathTest(unittest.TestCase):
    def test_accepts_paths_inside_the_workspace(self):
        self.assertEqual(clean_path("Reviewed/report.md"), "Reviewed/report.md")
        self.assertEqual(clean_path("./Reviewed/report.md"), "Reviewed/report.md")

    def test_rejects_escapes_and_hidden_files(self):
        for bad in ["", "/etc/passwd", "../x", "a/../../x", "..", ".box-mount/box-config.json", "Reviewed/.secret"]:
            with self.subTest(bad=bad), self.assertRaises(WorkspaceError):
                clean_path(bad)


class LocalWorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.ws = LocalWorkspace(self.dir.name)

    def test_write_read_list_delete(self):
        self.ws.write("Reviewed/a.md", "hello")
        self.assertEqual(self.ws.list(), ["Reviewed/a.md"])
        self.assertEqual(self.ws.read("Reviewed/a.md"), "hello")
        self.ws.delete("Reviewed/a.md")
        self.assertEqual(self.ws.list(), [])

    def test_never_overwrites(self):
        self.ws.write("a.md", "first")
        with self.assertRaises(WorkspaceError):
            self.ws.write("a.md", "second")
        self.assertEqual(self.ws.read("a.md"), "first")


class SandboxWorkspaceTest(unittest.TestCase):
    def test_runs_file_actions_inside_the_sandbox(self):
        done = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with mock.patch("subprocess.run", return_value=done) as run:
            SandboxWorkspace("demo-sandbox", "/sandbox/box", openshell="openshell --gateway g").delete("Reviewed/x.txt")
        command = run.call_args.args[0]
        self.assertEqual(command[:8], ["openshell", "--gateway", "g", "sandbox", "exec", "-n", "demo-sandbox", "--no-login-shell"])
        self.assertEqual(command[-2:], ["/sandbox/box", "Reviewed/x.txt"])

    def test_sandbox_errors_become_workspace_errors(self):
        failed = subprocess.CompletedProcess([], 3, stdout="", stderr="Already exists, not overwritten: a.md")
        with mock.patch("subprocess.run", return_value=failed), self.assertRaises(WorkspaceError):
            SandboxWorkspace("s", "/sandbox/box").write("a.md", "x")


def tool_call(name, arguments):
    return {"content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]}


class AgentWorkspaceToolsTest(unittest.TestCase):
    def setUp(self):
        mock.patch.dict(os.environ, {"NVIDIA_USE_REMOTE": "0"}).start()
        mock.patch.object(nemotron_agent, "remote_enabled", return_value=True).start()
        self.addCleanup(mock.patch.stopall)
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.ws = LocalWorkspace(self.dir.name)
        self.agent = NemotronAgent(SAMPLE, workspace=self.ws)
        self.agent.ingest()

    def run_with(self, replies, query="task"):
        with mock.patch.object(nemotron_agent, "chat_remote", side_effect=replies):
            return self.agent.ask(query, user="dev@example.com", groups={"workshop-attendees"})

    def test_workspace_tools_are_offered_only_with_a_workspace(self):
        names = {tool["function"]["name"] for tool in self.agent.tools}
        self.assertIn("delete_workspace_file", names)
        self.assertNotIn("delete_workspace_file", {tool["function"]["name"] for tool in NemotronAgent(SAMPLE).tools})

    def test_model_writes_a_file(self):
        out = self.run_with([tool_call("write_workspace_file", {"path": "Reviewed/r.md", "content": "# Review"}), {"content": "Written."}])
        self.assertEqual(out["status"], "ok")
        self.assertEqual(self.ws.read("Reviewed/r.md"), "# Review")
        tool_event = [e for e in out["trace"]["events"] if e["name"] == "tool"][0]
        self.assertEqual(tool_event["arguments"]["content"], "<8 characters>")

    def test_refused_write_reports_an_error_to_the_model(self):
        self.ws.write("Reviewed/r.md", "original")
        out = self.run_with([tool_call("write_workspace_file", {"path": "Reviewed/r.md", "content": "new"}), {"content": "It exists, stopped."}])
        self.assertEqual(self.ws.read("Reviewed/r.md"), "original")
        self.assertEqual([e for e in out["trace"]["events"] if e["name"] == "tool"][0]["status"], "error")

    def test_rate_limit_waits_and_continues(self):
        limited = RuntimeError("NVIDIA API error 429: Too Many Requests")
        with mock.patch.object(nemotron_agent.time, "sleep") as sleep:
            out = self.run_with([limited, {"content": "Nothing to do."}])
        sleep.assert_called_once_with(5)
        self.assertIn("llm_rate_limited", [e["name"] for e in out["trace"]["events"]])
        self.assertNotEqual(out["status"], "error")

    def test_model_failure_does_not_fall_back_when_files_may_have_changed(self):
        error = RuntimeError("NVIDIA API error 500")
        with mock.patch.object(nemotron_agent.time, "sleep"):
            out = self.run_with([tool_call("delete_workspace_file", {"path": "missing.txt"}), error, error, error])
        self.assertEqual(out["status"], "error")
        self.assertEqual(out["agent"], "nemotron")


if __name__ == "__main__":
    unittest.main()
