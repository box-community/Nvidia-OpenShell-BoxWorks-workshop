"""List what is really in a Box folder, straight from the Box API. Read-only.

    PYTHONPATH=src python3 -m akf_workshop.box_source.box_ls FOLDER_ID

Use it to check what reached Box, independently of the local copy that Box Mount syncs.
"""
from __future__ import annotations

import argparse

from .box_client import BoxClient


def main() -> int:
    parser = argparse.ArgumentParser(description="List a Box folder's files and subfolders, with their IDs")
    parser.add_argument("folder_id")
    args = parser.parse_args()
    client = BoxClient()
    folder = client.get(f"/folders/{args.folder_id}", {"fields": "name"})
    print(f"Box folder: {folder.get('name')}  (id {args.folder_id})")

    def walk(folder_id: str, prefix: str) -> None:
        for entry in client.paged(f"/folders/{folder_id}/items", {"fields": "id,name,type,size,modified_at"}):
            path = f"{prefix}{entry['name']}"
            if entry["type"] == "folder":
                print(f"  {path}/")
                walk(entry["id"], f"{path}/")
            else:
                print(f"  {path}  (file id {entry['id']}, {entry.get('size', 0)} bytes, modified {entry.get('modified_at', '')})")

    walk(args.folder_id, "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
