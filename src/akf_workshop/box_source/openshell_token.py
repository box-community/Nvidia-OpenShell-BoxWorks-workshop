"""Get a short-lived Box token on the laptop and hand it to OpenShell, never to the sandbox.

    PYTHONPATH=src python3 -m akf_workshop.box_source.openshell_token --sandbox box-agent

Uses BOX_CLIENT_ID, BOX_CLIENT_SECRET and BOX_ENTERPRISE_ID from your shell. Creates (or updates)
the OpenShell provider `box-token` from the `box-mount` profile and attaches it to the sandbox.
Inside, programs only see a placeholder; OpenShell swaps in the real token on approved Box requests.
Box tokens last about an hour: run this again to refresh, then restart Box Mount.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import time

from .box_client import BoxClient

PROVIDER = "box-token"
PROFILE = "box-mount"


def main() -> int:
    parser = argparse.ArgumentParser(description="Store a fresh Box token in OpenShell and attach it to a sandbox")
    parser.add_argument("--sandbox", required=True, help="The OpenShell sandbox that runs Box Mount")
    parser.add_argument("--dry-run", action="store_true", help="Print the OpenShell commands instead of running them")
    args = parser.parse_args()

    openshell = shlex.split(os.getenv("AKF_OPENSHELL", "openshell"))
    client = BoxClient()
    token = client.token()
    expires_at_ms = int(client._expires_at * 1000)
    # The token travels in the child process's environment, never on a command line or in output.
    env = {**os.environ, "BOX_ACCESS_TOKEN": token}
    env.pop("BOX_CLIENT_SECRET", None)

    def run(*command: str, with_token: bool = False) -> subprocess.CompletedProcess:
        full = [*openshell, *command]
        if args.dry_run:
            print("would run:", " ".join(shlex.quote(part) for part in full))
            return subprocess.CompletedProcess(full, 0, stdout='{"providers": []}', stderr="")
        return subprocess.run(full, env=env if with_token else None, capture_output=True, text=True, check=True)

    listed = run("provider", "list", "--output", "json")
    exists = any(p.get("name") == PROVIDER for p in json.loads(listed.stdout or "{}").get("providers", []))
    if exists:
        run("provider", "update", PROVIDER, "--credential", "BOX_ACCESS_TOKEN", "--wait", with_token=True)
    else:
        run("provider", "create", "--name", PROVIDER, "--type", PROFILE, "--credential", "BOX_ACCESS_TOKEN", with_token=True)
    run("provider", "update", PROVIDER, "--credential-expires-at", f"BOX_ACCESS_TOKEN={expires_at_ms}", "--wait")
    run("sandbox", "provider", "attach", args.sandbox, PROVIDER, "--wait")
    if args.dry_run:
        print("Dry run: nothing was changed.")
        return 0
    minutes = max(int((client._expires_at - time.time()) / 60), 0)
    print(f"Box token stored in OpenShell provider '{PROVIDER}' and attached to '{args.sandbox}'.")
    print(f"It expires in about {minutes} minutes. Programs in the sandbox see only a placeholder.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
