"""Lark/Feishu Drive integration - polls folder for new files and downloads them."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

LARK_API_BASE = "https://open.larksuite.com/open-apis"
FEISHU_API_BASE = "https://open.feishu.cn/open-apis"

PLATFORM_ALIASES: dict[str, str] = {
    "ig": "instagram", "instagram": "instagram",
    "instagram_personal": "instagram_personal",
    "fb": "facebook", "facebook": "facebook",
    "li": "linkedin", "linkedin": "linkedin",
    "linkedin_company": "linkedin_company",
    "linkedin_personal": "linkedin_personal",
    "tt": "tiktok", "tiktok": "tiktok",
    "yt": "youtube", "youtube": "youtube",
    "tw": "threads", "threads": "threads",
    "pin": "pinterest", "pinterest": "pinterest",
    "masto": "mastodon", "mastodon": "mastodon",
    "bsky": "bluesky", "bluesky": "bluesky",
    "gbiz": "google_business", "google_business": "google_business",
    "all": "all",
}

MEDIA_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".jpg", ".jpeg", ".png", ".gif", ".webp"}


class LarkClient:
    """Client for Lark/Feishu Open Platform API."""

    def __init__(self, app_id: str, app_secret: str, use_feishu: bool = False):
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = FEISHU_API_BASE if use_feishu else LARK_API_BASE
        self._tenant_token: str | None = None

    def _get_tenant_token(self) -> str:
        resp = httpx.post(
            f"{self.base_url}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Lark auth error: {data.get('msg')}")
        self._tenant_token = data["tenant_access_token"]
        return self._tenant_token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._tenant_token or self._get_tenant_token()}"}

    def _get(self, path: str, **kwargs) -> dict:
        resp = httpx.get(f"{self.base_url}{path}", headers=self._headers(), **kwargs)
        if resp.status_code == 401:
            self._tenant_token = None
            resp = httpx.get(f"{self.base_url}{path}", headers=self._headers(), **kwargs)
        resp.raise_for_status()
        return resp.json()

    def list_folder_files(self, folder_token: str) -> list[dict]:
        data = self._get("/drive/v1/files", params={"folder_token": folder_token, "page_size": 200}, timeout=15)
        if data.get("code") != 0:
            raise RuntimeError(f"Lark list_folder error: {data.get('msg')}")
        return data.get("data", {}).get("files", [])

    def list_media_files(self, folder_token: str) -> list[dict]:
        return [
            f for f in self.list_folder_files(folder_token)
            if f.get("type") == "file"
            and os.path.splitext(f.get("name", ""))[1].lower() in MEDIA_EXTENSIONS
        ]

    def list_subfolders(self, folder_token: str) -> list[dict]:
        return [f for f in self.list_folder_files(folder_token) if f.get("type") == "folder"]

    def get_file_tags(self, file_token: str) -> list[str]:
        try:
            data = self._get(f"/drive/v1/files/{file_token}/tags", timeout=10)
        except httpx.HTTPStatusError:
            return []
        if data.get("code") != 0:
            return []
        return [t.get("name", "").lower().strip() for t in data.get("data", {}).get("tags", []) if t.get("name")]

    def download_file(self, file_token: str, dest_path: str) -> str:
        resp = httpx.get(
            f"{self.base_url}/drive/v1/files/{file_token}/download",
            headers=self._headers(), timeout=300, follow_redirects=True,
        )
        if resp.status_code == 401:
            self._tenant_token = None
            resp = httpx.get(
                f"{self.base_url}/drive/v1/files/{file_token}/download",
                headers=self._headers(), timeout=300, follow_redirects=True,
            )
        resp.raise_for_status()
        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(resp.content)
        return dest_path


def resolve_platforms_from_folder_and_tags(
    folder_name: str,
    file_tags: list[str],
    all_platforms: list[str],
) -> list[str]:
    """Priority: file tags > folder name > all platforms."""
    tag_platforms = []
    for tag in file_tags:
        normalized = PLATFORM_ALIASES.get(tag.lower())
        if normalized == "all":
            return list(all_platforms)
        if normalized and normalized in all_platforms:
            tag_platforms.append(normalized)
    if tag_platforms:
        return list(dict.fromkeys(tag_platforms))
    folder_lower = folder_name.lower().strip()
    if folder_lower == "all":
        return list(all_platforms)
    p = PLATFORM_ALIASES.get(folder_lower)
    if p and p in all_platforms:
        return [p]
    return list(all_platforms)


def file_fingerprint(file_token: str, modified_time: str) -> str:
    return hashlib.md5(f"{file_token}:{modified_time}".encode()).hexdigest()
