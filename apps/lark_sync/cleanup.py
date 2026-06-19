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


def _archive_media_to_telegram(record) -> dict:
    """Upload the MediaAsset attached to this record to Telegram.

    Returns the telegram ref dict, or {} on failure (non-fatal).
    """
    if not record.post_id:
        return {}
    try:
        from apps.media_library.models import MediaAsset
        from providers.telegram_storage import upload_media

        asset = (
            MediaAsset.objects.filter(
                postmedia__post_id=record.post_id,
                source="lark",
            ).first()
        )
        if not asset or not asset.file:
            return {}

        caption = f"[archive] {record.file_name}"

        # Local storage: file is on disk
        if hasattr(asset.file, "path"):
            try:
                ref = upload_media(asset.file.path, caption=caption)
            except FileNotFoundError:
                return {}
        else:
            # S3: download to temp then upload
            import tempfile
            import requests as req
            with tempfile.NamedTemporaryFile(
                suffix=os.path.splitext(record.file_name)[1] or ".bin", delete=False
            ) as tmp:
                tmp_path = tmp.name
                resp = req.get(asset.file.url, timeout=120)
                resp.raise_for_status()
                tmp.write(resp.content)
            try:
                ref = upload_media(tmp_path, caption=caption)
            finally:
                os.unlink(tmp_path)

        logger.info("Archived '%s' → Telegram msg_id=%s", record.file_name, ref.get("message_id"))

        # Delete the actual file from S3/disk to free Supabase Storage quota
        try:
            asset.file.delete(save=False)
        except Exception:
            logger.warning("Could not delete file from storage for asset %s", asset.id)

        return ref
    except Exception:
        logger.warning("Telegram archive failed for '%s' (non-fatal)", record.file_name, exc_info=True)
        return {}


def run_cleanup() -> int:
    """Archive oldest ProcessedLarkFile records to Telegram, then remove from Supabase.

    Flow per record:
      1. If no telegram_storage yet → upload media to Telegram first (free archive).
      2. Delete the physical file from Supabase Storage to free quota.
      3. Detach Post FK and delete the ProcessedLarkFile row.

    Post/PlatformPost records are kept so the publish history remains intact.
    Returns the number of cleaned records.
    """
    from .models import ProcessedLarkFile

    total = _count_rows()
    target_count = int(ROW_LIMIT * CLEANUP_TARGET)
    to_delete = max(0, total - target_count)
    if to_delete == 0:
        return 0

    logger.info("Supabase cleanup: archiving & removing %d oldest records", to_delete)

    qs = list(ProcessedLarkFile.objects.order_by("created_at")[:to_delete])
    deleted = 0
    for record in qs:
        tg = record.telegram_storage or {}
        if not tg.get("message_id"):
            tg_ref = _archive_media_to_telegram(record)
            if tg_ref:
                record.telegram_storage = tg_ref
                record.save(update_fields=["telegram_storage"])

        # Detach Post FK; keep Post itself for history
        record.post = None
        record.save(update_fields=["post"])
        record.delete()
        deleted += 1

    logger.info("Supabase cleanup complete: %d records archived & removed", deleted)
    return deleted
