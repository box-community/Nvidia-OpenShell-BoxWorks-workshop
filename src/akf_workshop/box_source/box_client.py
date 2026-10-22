"""Minimal Box API client using Client Credentials Grant, in plain HTTP so there is nothing to install.

Needs BOX_CLIENT_ID, BOX_CLIENT_SECRET and BOX_ENTERPRISE_ID. The code acts as the app's service
account, so it sees only content that account owns or has been invited to as a collaborator.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

API = "https://api.box.com/2.0"
UPLOAD = "https://upload.box.com/api/2.0"
TOKEN_URL = "https://api.box.com/oauth2/token"
CREDENTIAL_VARS = ("BOX_CLIENT_ID", "BOX_CLIENT_SECRET", "BOX_ENTERPRISE_ID")


class BoxError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"Box API error {status}: {body[:300]}")
        self.status = status
        self.body = body


def box_configured() -> bool:
    return all(os.getenv(name) for name in CREDENTIAL_VARS)


class BoxClient:
    def __init__(self) -> None:
        self._token = ""
        self._expires_at = 0.0

    def token(self) -> str:
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        missing = [name for name in CREDENTIAL_VARS if not os.getenv(name)]
        if missing:
            raise RuntimeError(f"Box credentials missing: set {', '.join(missing)}")
        form = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": os.environ["BOX_CLIENT_ID"],
                "client_secret": os.environ["BOX_CLIENT_SECRET"],
                "box_subject_type": "enterprise",
                "box_subject_id": os.environ["BOX_ENTERPRISE_ID"],
            }
        ).encode()
        request = urllib.request.Request(TOKEN_URL, data=form, headers={"Content-Type": "application/x-www-form-urlencoded"})
        response = self._send(request)
        self._token = response["access_token"]
        self._expires_at = time.time() + float(response.get("expires_in", 3600))
        return self._token

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        return self._send(urllib.request.Request(f"{API}{path}{query}", headers=self._auth()))

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        headers = {**self._auth(), "Content-Type": "application/json"}
        return self._send(urllib.request.Request(f"{API}{path}", data=json.dumps(body).encode(), headers=headers, method="POST"))

    def paged(self, path: str, params: dict[str, Any] | None = None, limit: int = 1000) -> list[dict[str, Any]]:
        """All entries of an offset-paginated collection."""
        entries: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self.get(path, {**(params or {}), "limit": limit, "offset": offset})
            entries.extend(page.get("entries", []))
            offset += limit
            if offset >= int(page.get("total_count", 0)) or not page.get("entries"):
                return entries

    def download(self, file_id: str) -> bytes:
        return self._send(urllib.request.Request(f"{API}/files/{file_id}/content", headers=self._auth()), raw=True)

    def upload(self, parent_id: str, name: str, data: bytes) -> dict[str, Any]:
        boundary = uuid.uuid4().hex
        attributes = json.dumps({"name": name, "parent": {"id": parent_id}})
        body = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="attributes"\r\n\r\n{attributes}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
        headers = {**self._auth(), "Content-Type": f"multipart/form-data; boundary={boundary}"}
        response = self._send(urllib.request.Request(f"{UPLOAD}/files/content", data=body, headers=headers, method="POST"))
        return response["entries"][0]

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token()}"}

    def _send(self, request: urllib.request.Request, raw: bool = False) -> Any:
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
        except urllib.error.HTTPError as exc:
            raise BoxError(exc.code, exc.read().decode("utf-8", errors="replace")) from exc
        return data if raw else json.loads(data.decode("utf-8") or "{}")
