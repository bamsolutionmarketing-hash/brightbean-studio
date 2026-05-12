"""Supabase storage auto-cleanup: delete oldest records when usage >= 80%."""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

# Supabase free tier: 500 MB database, 1 GB file storage
# We track DB row count as a proxy since querying actual bytes requires admin API.
# Default safe limit: 50 000 rows total across lark_sync tables.
ROW_LIMIT = int(os.environ.get("SUPABASE_ROW_LIMIT", "50000"))
CLEANUP_THRESHOLD = float(os.environ.get("SUPABASE_CLEANUP_THRESHOLD", "0.80"))
CLEANUP_TARGET = float(os.environ.get("SUPABASE_CLEANUP_TARGET", "0.60"))


def _count_rows() -> int:
    from .models import ProcessedLarkFile
    return ProcessedLarkFile.objects.count()


def _get_supabase_storage_bytes() -> int | None:
    """Query Supabase Management API for actual storage usage (bytes).

    Returns None if the API is not configured or the call fails.
    Requires SUPABASE_PROJECT_REF and SUPABASE_SERVICE_ROLE_KEY env vars.
    """
    project_ref = os.environ.get("SUPABASE_PROJECT_REF", "")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not project_ref or not service_key:
        return None
    try:
        url = f"https://api.supabase.com/v1/projects/{project_ref}/usage"
        headers = {"Authorization": f"Bearer {service_key}"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # Response shape: {"db_size": <bytes>, "storage_size": <bytes>, ...}
        db_bytes = data.get("db_size") or data.get("database", {}).get("usage", 0)
        storage_bytes = data.get("storage_size") or data.get("storage", {}).get("usage", 0)
        return (db_bytes or 0) + (storage_bytes or 0)
    except Exception:
        logger.debug("Could not fetch Supabase usage via API", exc_info=True)
        return None


def needs_cleanup() -> bool:
    """Return True if storage is at or above the cleanup threshold."""
    used_bytes = _get_supabase_storage_bytes()
    if used_bytes is not None:
        # Supabase free tier total quota: 500 MB DB + 1 GB storage ≈ 1.5 GB
        quota = int(os.environ.get("SUPABASE_QUOTA_BYTES", str(500 * 1024 * 1024)))
        ratio = used_bytes / quota
        logger.debug("Supabase usage: %d / %d bytes (%.1f%%)", used_bytes, quota, ratio * 100)
        return ratio >= CLEANUP_THRESHOLD

    # Fallback: row-count heuristic
    count = _count_rows()
    ratio = count / ROW_LIMIT
    logger.debug("ProcessedLarkFile rows: %d / %d (%.1f%%)", count, ROW_LIMIT, ratio * 100)
    return ratio >= CLEANUP_THRESHOLD


def run_cleanup() -> int:
    """Delete oldest ProcessedLarkFile records (and associated Telegram refs) until
    usage drops below CLEANUP_TARGET.  Returns the number of deleted records."""
    from .models import ProcessedLarkFile
    from providers.telegram_storage import delete_message

    total = _count_rows()
    target_count = int(ROW_LIMIT * CLEANUP_TARGET)
    to_delete = max(0, total - target_count)
    if to_delete == 0:
        return 0

    logger.info("Supabase cleanup: removing %d oldest ProcessedLarkFile records", to_delete)

    qs = ProcessedLarkFile.objects.order_by("created_at")[:to_delete]
    deleted = 0
    for record in qs:
        # Remove Telegram copy if we stored one
        tg = record.telegram_storage or {}
        msg_id = tg.get("message_id")
        channel_id = tg.get("channel_id")
        if msg_id and channel_id:
            delete_message(msg_id)

        # Detach the Post FK to avoid cascade delete of content the user might still want
        record.post = None
        record.delete()
        deleted += 1

    logger.info("Supabase cleanup complete: removed %d records", deleted)
    return deleted
