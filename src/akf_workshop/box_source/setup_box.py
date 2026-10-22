"""Create the workshop's folder, groups and files in Box, and print the BOX_FOLDER_ID to use.

    PYTHONPATH=src python3 -m akf_workshop.box_source.setup_box

    PYTHONPATH=src python3 -m akf_workshop.box_source.setup_box --agent-workspace [--invite you@example.com]

Safe to run again: existing folders, groups, collaborations and files are reused, not duplicated.
Box permissions are inherited downwards, so restricted files get their own folder:

    Context-Aware Agents Workshop/
      docs/           shared with group workshop-attendees
      data/           shared with group workshop-attendees
      support-leads/  shared with group support-leads
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .box_client import BoxClient, BoxError

WORKSHOP_FOLDER = "Context-Aware Agents Workshop"
AGENT_WORKSPACE_FOLDER = "Agent Workspace"  # what Box Mount syncs: only what the agent may change
# (local file under sample_box, Box subfolder, group that may see it)
LAYOUT = [
    ("docs/box-ai-retrieval.md", "docs", "workshop-attendees"),
    ("docs/supply-chain-risk-playbook.md", "docs", "workshop-attendees"),
    ("data/accounts.csv", "data", "workshop-attendees"),
    ("docs/enterprise-support-policy.md", "support-leads", "support-leads"),
    ("data/support_cases.csv", "support-leads", "support-leads"),
]


def ensure_folder(client: BoxClient, parent_id: str, name: str) -> str:
    try:
        return client.post("/folders", {"name": name, "parent": {"id": parent_id}})["id"]
    except BoxError as exc:
        if exc.status != 409:
            raise
    for entry in client.paged(f"/folders/{parent_id}/items", {"fields": "id,name,type"}):
        if entry["type"] == "folder" and entry["name"] == name:
            return entry["id"]
    raise RuntimeError(f"Folder {name!r} exists but could not be found")


def ensure_group(client: BoxClient, name: str) -> str:
    for group in client.paged("/groups", {"filter_term": name}):
        if group["name"] == name:
            return group["id"]
    return client.post("/groups", {"name": name})["id"]


def ensure_group_collaboration(client: BoxClient, folder_id: str, group_id: str) -> None:
    existing = client.get(f"/folders/{folder_id}/collaborations").get("entries", [])
    if any((c.get("accessible_by") or {}).get("id") == group_id for c in existing):
        return
    client.post(
        "/collaborations",
        {"item": {"type": "folder", "id": folder_id}, "accessible_by": {"type": "group", "id": group_id}, "role": "viewer"},
    )


def ensure_file(client: BoxClient, folder_id: str, path: Path) -> str:
    for entry in client.paged(f"/folders/{folder_id}/items", {"fields": "id,name,type"}):
        if entry["type"] == "file" and entry["name"] == path.name:
            return entry["id"]
    return client.upload(folder_id, path.name, path.read_bytes())["id"]


def ensure_user_collaboration(client: BoxClient, folder_id: str, login: str) -> str:
    """Invite a Box user (by login email) as an editor, so they can see the folder in their own Box."""
    wanted = login.strip().lower()
    for collaboration in client.get(f"/folders/{folder_id}/collaborations").get("entries", []):
        # A user in your Box enterprise is listed by login; an outside address is a pending invite_email.
        who = ((collaboration.get("accessible_by") or {}).get("login") or collaboration.get("invite_email") or "").lower()
        if who == wanted:
            return f"already invited ({collaboration.get('status', 'unknown')})"
    try:
        collaboration = client.post(
            "/collaborations",
            {"item": {"type": "folder", "id": folder_id}, "accessible_by": {"type": "user", "login": login}, "role": "editor"},
        )
    except BoxError as exc:
        if "user_already_collaborator" in exc.body:
            return "already invited"
        raise
    return collaboration.get("status", "invited")


def setup_agent_workspace(client: BoxClient, parent_id: str, invite: str | None) -> str:
    folder_id = ensure_folder(client, parent_id, AGENT_WORKSPACE_FOLDER)
    print(f"folder   {AGENT_WORKSPACE_FOLDER}  (id {folder_id})")
    reviewed_id = ensure_folder(client, folder_id, "Reviewed")
    print(f"folder   {AGENT_WORKSPACE_FOLDER}/Reviewed  (id {reviewed_id})")
    if invite:
        print(f"invite   {invite} as editor: {ensure_user_collaboration(client, folder_id, invite)}")
    print(f"\nDone. Mount this folder with Box Mount:\n  export AGENT_FOLDER_ID={folder_id}")
    print(f"  https://app.box.com/folder/{folder_id}")
    return folder_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the workshop folder, groups and files in Box")
    parser.add_argument("--sample-box", default="sample_box")
    parser.add_argument("--parent-id", default="0", help="Box folder to create the workshop folder in (0 = the service account's root)")
    parser.add_argument("--agent-workspace", action="store_true", help="Create the 'Agent Workspace' folder for Box Mount instead")
    parser.add_argument("--invite", metavar="EMAIL", help="With --agent-workspace: invite this Box user as an editor")
    args = parser.parse_args()
    client = BoxClient()
    if args.agent_workspace:
        setup_agent_workspace(client, args.parent_id, args.invite)
        return 0
    root_id = ensure_folder(client, args.parent_id, WORKSHOP_FOLDER)
    print(f"folder   {WORKSHOP_FOLDER}  (id {root_id})")
    groups = {name: ensure_group(client, name) for name in sorted({group for _, _, group in LAYOUT})}
    for name, group_id in groups.items():
        print(f"group    {name}  (id {group_id})")
    subfolders: dict[str, str] = {}
    for local, subfolder, group in LAYOUT:
        if subfolder not in subfolders:
            subfolders[subfolder] = ensure_folder(client, root_id, subfolder)
            ensure_group_collaboration(client, subfolders[subfolder], groups[group])
            print(f"folder   {subfolder}/  shared with {group}")
        file_id = ensure_file(client, subfolders[subfolder], Path(args.sample_box) / local)
        print(f"file     {subfolder}/{Path(local).name}  (id {file_id})")
    print(f"\nDone. Use this folder:\n  export BOX_FOLDER_ID={root_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
