from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AccessControl:
    users: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()

    def allows(self, user: str, groups: set[str]) -> bool:
        if user in self.users:
            return True
        return bool(groups.intersection(self.groups))


@dataclass(frozen=True)
class BoxFile:
    file_id: str
    name: str
    path: str
    relative_path: str
    mime_type: str
    version: str
    owner: str
    modified_at: str
    labels: tuple[str, ...] = field(default_factory=tuple)
    acl: AccessControl = field(default_factory=AccessControl)
    content: str = ""
    content_bytes: bytes = b""
