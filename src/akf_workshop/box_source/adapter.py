from __future__ import annotations

import hashlib
import json
import mimetypes
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .schema import AccessControl, BoxFile


class BoxPlaceholderAdapter:
    """Box-shaped adapter over local workshop files.

    Replace this class with Box SDK calls later. Keep the returned BoxFile
    contract stable so the search and agent layers do not need to change.
    """

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.permissions = self._load_permissions()

    def list_files(self) -> list[BoxFile]:
        files: list[BoxFile] = []
        for path in sorted(self.root.rglob("*")):
            if path.is_file() and path.name != "permissions.json":
                files.append(self._to_box_file(path, include_content=False))
        return files

    def get_file(self, file_id: str) -> BoxFile:
        for path in sorted(self.root.rglob("*")):
            if path.is_file() and path.name != "permissions.json":
                box_file = self._to_box_file(path, include_content=False)
                if box_file.file_id == file_id:
                    return replace(box_file, **_read_content(path, box_file.mime_type))
        raise KeyError(f"Unknown file_id: {file_id}")

    def iter_changed_files(self, since: datetime | None = None) -> list[BoxFile]:
        if since is None:
            return self.list_files()
        changed = []
        for file in self.list_files():
            modified = datetime.fromisoformat(file.modified_at.replace("Z", "+00:00"))
            if modified > since:
                changed.append(file)
        return changed

    def _load_permissions(self) -> dict:
        path = self.root / "permissions.json"
        if not path.exists():
            return {"default_acl": {"users": [], "groups": ["workshop-attendees"]}, "overrides": {}}
        return json.loads(path.read_text(encoding="utf-8"))

    def _to_box_file(self, path: Path, include_content: bool) -> BoxFile:
        relative = path.relative_to(self.root).as_posix()
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
        digest = hashlib.sha1(relative.encode("utf-8")).hexdigest()[:12]
        mime_type = mimetypes.guess_type(path.name)[0] or "text/plain"
        labels = tuple(part for part in relative.split("/")[:-1] if part)
        acl = self._acl_for(relative)
        return BoxFile(
            file_id=f"box-{digest}",
            name=path.name,
            path=f"/Box Placeholder/{relative}",
            relative_path=relative,
            mime_type=mime_type,
            version=f"v{int(stat.st_mtime)}",
            owner="box-devday@example.com",
            modified_at=modified,
            labels=labels,
            acl=acl,
            **(_read_content(path, mime_type) if include_content else {}),
        )

    def _acl_for(self, relative_path: str) -> AccessControl:
        raw = self.permissions.get("overrides", {}).get(relative_path, self.permissions.get("default_acl", {}))
        return AccessControl(users=tuple(raw.get("users", [])), groups=tuple(raw.get("groups", [])))


TEXT_MIME_TYPES = {"application/json", "application/csv"}
TEXT_SUFFIXES = {".md", ".csv", ".txt", ".json"}


def _is_text(path: Path, mime_type: str) -> bool:
    return mime_type.startswith("text/") or mime_type in TEXT_MIME_TYPES or path.suffix.lower() in TEXT_SUFFIXES


def _read_content(path: Path, mime_type: str) -> dict:
    """Text files fill `content`; everything else fills `content_bytes`, so binaries never abort ingest."""
    if _is_text(path, mime_type):
        try:
            return {"content": path.read_text(encoding="utf-8"), "content_bytes": b""}
        except UnicodeDecodeError:  # an unknown extension guessed as text/plain but holding binary data
            pass
    return {"content": "", "content_bytes": path.read_bytes()}
