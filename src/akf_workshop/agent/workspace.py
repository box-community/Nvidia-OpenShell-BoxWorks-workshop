"""The agent's "hands": file tools that act on a workspace folder.

`SandboxWorkspace` runs every file action inside an OpenShell sandbox through `openshell sandbox exec`,
so the agent's writes and deletes happen where Box Mount syncs them and where OpenShell's network
policy decides what reaches Box. The model itself runs on the laptop and never touches the files or
the Box token. `LocalWorkspace` does the same on a local folder, for trying the tools without OpenShell.
"""
from __future__ import annotations

import base64
import os
import posixpath
import shlex
import subprocess
from pathlib import Path

MAX_READ_BYTES = 20000


class WorkspaceError(RuntimeError):
    pass


def clean_path(relative: str) -> str:
    """A path inside the workspace: relative, no '..', no hidden segments."""
    raw = str(relative or "").strip()
    if raw.startswith("./"):
        raw = raw[2:]
    path = posixpath.normpath(raw) if raw else ""
    if not path or path == "." or path.startswith("/") or path == ".." or path.startswith("../"):
        raise WorkspaceError(f"Path must be a file inside the workspace: {relative!r}")
    if any(part.startswith(".") for part in path.split("/")):
        raise WorkspaceError(f"Hidden files and folders are off limits: {relative!r}")
    return path


class LocalWorkspace:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.label = f"local folder {self.root}"

    def list(self) -> list[str]:
        return sorted(
            str(path.relative_to(self.root)).replace(os.sep, "/")
            for path in self.root.rglob("*")
            if path.is_file() and not any(part.startswith(".") for part in path.relative_to(self.root).parts)
        )

    def read(self, relative: str) -> str:
        path = self.root / clean_path(relative)
        if not path.is_file():
            raise WorkspaceError(f"No such file: {relative}")
        return path.read_bytes()[:MAX_READ_BYTES].decode("utf-8", errors="replace")

    def write(self, relative: str, text: str) -> None:
        path = self.root / clean_path(relative)
        if path.exists():
            raise WorkspaceError(f"Already exists, not overwritten: {relative}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def delete(self, relative: str) -> None:
        path = self.root / clean_path(relative)
        if not path.is_file():
            raise WorkspaceError(f"No such file: {relative}")
        path.unlink()


class SandboxWorkspace:
    """File actions inside an OpenShell sandbox. `openshell` is the CLI command, e.g. "openshell --gateway box-demo"."""

    def __init__(self, sandbox: str, root: str, openshell: str | None = None):
        self.sandbox = sandbox
        self.root = root.rstrip("/") or "/"
        self.openshell = shlex.split(openshell or os.getenv("AKF_OPENSHELL", "openshell"))
        self.label = f"OpenShell sandbox {sandbox}:{self.root}"

    def list(self) -> list[str]:
        out = self._run('cd "$1" && find . -type f -not -path "*/.*" -printf "%P\\n" | sort')
        return [line for line in out.splitlines() if line]

    def read(self, relative: str) -> str:
        return self._run(f'test -f "$1/$2" || {{ echo "No such file: $2" >&2; exit 2; }}; head -c {MAX_READ_BYTES} "$1/$2"', clean_path(relative))

    def write(self, relative: str, text: str) -> None:
        encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
        self._run(
            'if [ -e "$1/$2" ]; then echo "Already exists, not overwritten: $2" >&2; exit 3; fi; '
            'mkdir -p "$(dirname "$1/$2")" && printf %s "$3" | base64 -d > "$1/$2"',
            clean_path(relative),
            encoded,
        )

    def delete(self, relative: str) -> None:
        self._run('test -f "$1/$2" || { echo "No such file: $2" >&2; exit 2; }; rm -- "$1/$2"', clean_path(relative))

    def _run(self, script: str, *args: str) -> str:
        command = [*self.openshell, "sandbox", "exec", "-n", self.sandbox, "--no-login-shell", "--", "/bin/sh", "-c", script, "sh", self.root, *args]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise WorkspaceError(f"Could not reach the sandbox: {exc}") from exc
        if result.returncode != 0:
            raise WorkspaceError((result.stderr or result.stdout).strip()[-300:] or f"exit code {result.returncode}")
        return result.stdout
