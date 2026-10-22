"""Box adapter over the real Box API, returning the same `BoxFile` contract as the placeholder.

Point it at a folder with BOX_FOLDER_ID. Permissions come from Box collaborations: a file's ACL is
its owner plus every user and group collaborating on the file or on any folder above it inside the
workshop folder (Box permissions are inherited downwards).

Permissions are read live on every run. File contents are cached on disk by Box file version, which
never changes once written, so a file is downloaded again only after someone edits it.
"""
from __future__ import annotations

import mimetypes
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from .box_client import BoxClient
from .schema import AccessControl, BoxFile

TEXT_SUFFIXES = (".md", ".csv", ".txt", ".json")
FILE_FIELDS = "id,name,type,file_version,modified_at,owned_by"


class BoxApiAdapter:
    def __init__(self, folder_id: str, client: BoxClient | None = None):
        self.folder_id = str(folder_id)
        self.client = client or BoxClient()
        self.folder_name = ""
        self._files: dict[str, BoxFile] | None = None

    def list_files(self) -> list[BoxFile]:
        if self._files is None:
            root = self.client.get(f"/folders/{self.folder_id}", {"fields": "id,name"})
            self.folder_name = root.get("name", self.folder_id)
            files: dict[str, BoxFile] = {}
            self._walk(self.folder_id, prefix="", inherited=self._collaborators("folders", self.folder_id), files=files)
            self._files = files
        return sorted(self._files.values(), key=lambda box_file: box_file.relative_path)

    def get_file(self, file_id: str) -> BoxFile:
        listed = {box_file.file_id: box_file for box_file in self.list_files()}.get(file_id)
        if listed is None:
            raise KeyError(f"Unknown file_id: {file_id}")
        data = self._content(listed)
        if listed.name.lower().endswith(TEXT_SUFFIXES) or listed.mime_type.startswith("text/"):
            try:
                return replace(listed, content=data.decode("utf-8"), content_bytes=b"")
            except UnicodeDecodeError:
                pass
        return replace(listed, content="", content_bytes=data)

    def iter_changed_files(self, since: datetime | None = None) -> list[BoxFile]:
        if since is None:
            return self.list_files()
        return [f for f in self.list_files() if datetime.fromisoformat(f.modified_at.replace("Z", "+00:00")) > since]

    def _content(self, box_file: BoxFile) -> bytes:
        cache = Path(os.getenv("AKF_CACHE_DIR", ".akf_cache")) / "box" / f"{box_file.file_id}-{box_file.version}"
        if cache.exists():
            return cache.read_bytes()
        data = self.client.download(box_file.file_id.removeprefix("box-"))
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache.with_suffix(".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, cache)
        return data

    def _walk(self, folder_id: str, prefix: str, inherited: tuple[set[str], set[str]], files: dict[str, BoxFile]) -> None:
        entries = self.client.paged(f"/folders/{folder_id}/items", {"fields": FILE_FIELDS})
        # One collaborations call per item; run them in parallel since each is a separate round trip.
        with ThreadPoolExecutor(max_workers=8) as pool:
            collaborators = list(pool.map(lambda e: self._collaborators(f"{e['type']}s", e["id"]), entries))
        for entry, (users, groups) in zip(entries, collaborators):
            relative = f"{prefix}{entry['name']}"
            if entry["type"] == "folder":
                self._walk(entry["id"], f"{relative}/", (inherited[0] | users, inherited[1] | groups), files)
            elif entry["type"] == "file":
                owner = (entry.get("owned_by") or {}).get("login", "")
                acl_users = inherited[0] | users | ({owner} if owner else set())
                files[f"box-{entry['id']}"] = BoxFile(
                    file_id=f"box-{entry['id']}",
                    name=entry["name"],
                    path=f"/Box/{self.folder_name}/{relative}",
                    relative_path=relative,
                    mime_type=mimetypes.guess_type(entry["name"])[0] or "application/octet-stream",
                    version=f"v{(entry.get('file_version') or {}).get('id', '0')}",
                    owner=owner,
                    modified_at=entry.get("modified_at", ""),
                    labels=tuple(part for part in prefix.split("/") if part),
                    acl=AccessControl(users=tuple(sorted(acl_users)), groups=tuple(sorted(inherited[1] | groups))),
                )

    def _collaborators(self, kind: str, item_id: str) -> tuple[set[str], set[str]]:
        """Accepted collaborators on one file or folder: (user logins, group names)."""
        users: set[str] = set()
        groups: set[str] = set()
        for collaboration in self.client.get(f"/{kind}/{item_id}/collaborations").get("entries", []):
            if collaboration.get("status") not in (None, "accepted"):
                continue
            who = collaboration.get("accessible_by") or {}
            if who.get("type") == "group" and who.get("name"):
                groups.add(who["name"])
            elif who.get("type") == "user" and who.get("login"):
                users.add(who["login"])
        return users, groups
