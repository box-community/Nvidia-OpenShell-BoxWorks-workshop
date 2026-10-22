from __future__ import annotations

import argparse
import json
from pathlib import Path

from akf_workshop.nvidia_clients import remote_enabled

from .harness import AgentHarness
from .nemotron_agent import NemotronAgent


def main() -> int:
    parser = argparse.ArgumentParser(description="Box + NVIDIA AKF workshop CLI")
    parser.add_argument("--sample-box", default="sample_box", help="Path to the sample Box folder")
    parser.add_argument("--user", default="dev@example.com")
    parser.add_argument("--groups", default="workshop-attendees", help="Comma-separated group names")
    parser.add_argument(
        "--agent",
        choices=["rules", "nemotron"],
        default="rules",
        help="rules: keyword routing, answer quoted from the best chunk (offline). nemotron: hosted Nemotron 3.5 Super picks tools and writes the answer (remote mode)",
    )
    parser.add_argument("--workspace", help="With --agent nemotron: give the agent file tools on this folder (a Box Mount folder)")
    parser.add_argument("--sandbox", help="With --workspace: run the file tools inside this OpenShell sandbox (CLI from AKF_OPENSHELL, default 'openshell')")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("ingest")

    ask_parser = subparsers.add_parser("ask")
    ask_parser.add_argument("query")

    args = parser.parse_args()
    root = Path(args.sample_box)
    groups = {group.strip() for group in args.groups.split(",") if group.strip()}
    if args.agent == "nemotron":
        if not remote_enabled():
            parser.error("--agent nemotron needs remote mode: set NVIDIA_API_KEY and NVIDIA_USE_REMOTE=1")
        workspace = None
        if args.workspace:
            from .workspace import LocalWorkspace, SandboxWorkspace

            workspace = SandboxWorkspace(args.sandbox, args.workspace) if args.sandbox else LocalWorkspace(args.workspace)
        harness = NemotronAgent(root, workspace=workspace)
    else:
        harness = AgentHarness(root)
    ingest_result = harness.ingest()

    if args.command == "ingest":
        print(json.dumps(ingest_result, indent=2))
        return 0
    if args.command == "ask":
        print(json.dumps(harness.ask(args.query, user=args.user, groups=groups), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
