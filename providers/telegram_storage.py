"""Telegram Bot API used as free unlimited cloud storage for media files."""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_BOT_TOKEN = None
_CHANNEL_ID = None


def _cfg():
    global _BOT_TOKEN, _CHANNEL_ID
    if _BOT_TOKEN is None:
        from django.conf import settings
        _BOT_TOKEN = getattr(settings, "TELEGRAM_BOT_TOKEN", os.environ.get("TELEGRAM_BOT_TOKEN", ""))
        _CHANNEL_ID = getattr(settings, "TELEGRAM_STORAGE_CHANNEL_ID", os.environ.get("TELEGRAM_STORAGE_CHANNEL_ID", ""))
    return _BOT_TOKEN, _CHANNEL_ID


def _api(method: str, **kwargs) -> dict:
    token, _ = _cfg()
    url = f"https://api.telegram.org/bot{token}/{method}"
    resp = requests.post(url, timeout=120, **kwargs)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data.get('description')}")
    return data["result"]


def upload_media(file_path: str, caption: str = "") -> dict:
    """Upload a media file to the Telegram storage channel.

    Returns a dict with keys: file_id, file_unique_id, message_id, media_type
    """
    _, channel_id = _cfg()
    if not channel_id:
        raise RuntimeError("TELEGRAM_STORAGE_CHANNEL_ID not configured")

    path = Path(file_path)
    ext = path.suffix.lower()
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    is_video = ext in {".mp4", ".mov", ".avi", ".mkv", ".webm"}

    method = "sendVideo" if is_video else "sendPhoto"
    field = "video" if is_video else "photo"

    # Telegram photo limit: 10 MB. For larger images send as document.
    if not is_video and path.stat().st_size > 10 * 1024 * 1024:
        method = "sendDocument"
        field = "document"

    with open(file_path, "rb") as fh:
        result = _api(
            method,
            data={"chat_id": channel_id, "caption": caption[:1024] if caption else ""},
            files={field: (path.name, fh, mime)},
        )

    msg_id = result["message_id"]
    if is_video:
        file_obj = result.get("video") or result.get("document")
    elif field == "document":
        file_obj = result.get("document")
    else:
        # photo returns list sorted by size; last = largest
        photos = result.get("photo", [])
        file_obj = photos[-1] if photos else {}

    return {
        "message_id": msg_id,
        "file_id": file_obj.get("file_id", ""),
        "file_unique_id": file_obj.get("file_unique_id", ""),
        "media_type": "video" if is_video else "image",
        "channel_id": channel_id,
    }


def get_download_url(file_id: str) -> str:
    """Return a temporary direct download URL for a Telegram file_id."""
    token, _ = _cfg()
    info = _api("getFile", data={"file_id": file_id})
    file_path = info.get("file_path", "")
    return f"https://api.telegram.org/file/bot{token}/{file_path}"


def delete_message(message_id: int) -> bool:
    """Delete a previously uploaded message/media from the storage channel."""
    _, channel_id = _cfg()
    try:
        _api("deleteMessage", data={"chat_id": channel_id, "message_id": message_id})
        return True
    except Exception:
        logger.warning("Could not delete Telegram message %s", message_id)
        return False
