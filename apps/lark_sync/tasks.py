"""Background tasks: poll Lark Drive and dispatch new files to the publisher."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from background_task import background
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path(getattr(settings, "MEDIA_ROOT", "/tmp")) / "lark_downloads"


@background(schedule=0)
def poll_all_lark_folders():
    """Poll every active LarkWatchConfig. Called by the background worker."""
    from .models import LarkWatchConfig

    for config in LarkWatchConfig.objects.filter(is_active=True).select_related("workspace"):
        try:
            _poll_lark_folder(config)
        except Exception:
            logger.exception("Error polling Lark folder %s", config.folder_token)


def _poll_lark_folder(config) -> int:
    from providers.lark import LarkClient, file_fingerprint

    from .models import ProcessedLarkFile

    app_id = getattr(settings, "LARK_APP_ID", "")
    app_secret = getattr(settings, "LARK_APP_SECRET", "")
    use_feishu = getattr(settings, "LARK_USE_FEISHU", False)

    if not app_id or not app_secret:
        logger.warning("LARK_APP_ID / LARK_APP_SECRET not configured -- skipping poll")
        return 0

    client = LarkClient(app_id, app_secret, use_feishu=use_feishu)

    # Scan root folder + all subfolders
    folders_to_scan = [{"token": config.folder_token, "name": config.folder_name or "all"}]
    try:
        for sf in client.list_subfolders(config.folder_token):
            folders_to_scan.append({"token": sf["token"], "name": sf["name"]})
    except Exception:
        logger.exception("Failed to list subfolders for %s", config.folder_token)

    processed_count = 0
    for folder in folders_to_scan:
        try:
            files = client.list_media_files(folder["token"])
        except Exception:
            logger.exception("Failed to list files in folder %s", folder["token"])
            continue

        for f in files:
            file_token = f.get("token", "")
            modified = f.get("modified_time", "") or f.get("created_time", "")
            fingerprint = file_fingerprint(file_token, str(modified))

            existing = ProcessedLarkFile.objects.filter(file_token=file_token).first()
            if existing and existing.fingerprint == fingerprint:
                continue  # unchanged, already processed

            try:
                processed_count += _process_lark_file(client, f, folder, fingerprint, config, existing)
            except Exception:
                logger.exception("Failed to process Lark file %s (%s)", f.get("name"), file_token)

    return processed_count


def _process_lark_file(client, file_info, folder, fingerprint, config, existing) -> int:
    from providers.lark import resolve_platforms_from_folder_and_tags

    from apps.social_accounts.models import SocialAccount

    from .models import ProcessedLarkFile

    file_token = file_info["token"]
    file_name = file_info.get("name", "untitled")

    tags = client.get_file_tags(file_token)

    connected_platforms = list(
        SocialAccount.objects.filter(
            workspace=config.workspace,
            connection_status="connected",
        ).values_list("platform", flat=True).distinct()
    )
    target_platforms = resolve_platforms_from_folder_and_tags(
        folder_name=folder["name"],
        file_tags=tags,
        all_platforms=connected_platforms,
    )

    if not target_platforms:
        logger.info("No matching connected accounts for '%s' -- skipping", file_name)
        return 0

    ext = os.path.splitext(file_name)[1] or ".tmp"
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = str(DOWNLOAD_DIR / f"{file_token}{ext}")
    client.download_file(file_token, dest_path)
    logger.info("Downloaded: %s -> %s", file_name, dest_path)

    # Generate AI caption (or fallback to hashtags from non-platform tags)
    platform_set = set(target_platforms)
    content_tags = [t for t in tags if t not in platform_set]

    from providers.ai_caption import generate_caption

    # Generate one caption per platform (tone differs per platform)
    captions_by_platform: dict[str, str] = {}
    for platform in target_platforms:
        captions_by_platform[platform] = generate_caption(
            file_name=file_name,
            platform=platform,
            tags=content_tags,
        )

    # Use the first platform's caption as the default post caption
    caption = next(iter(captions_by_platform.values()), "")

    post = _create_post_for_file(
        workspace=config.workspace,
        file_path=dest_path,
        file_name=file_name,
        caption=caption,
        target_platforms=target_platforms,
        captions_by_platform=captions_by_platform,
    )

    if existing:
        existing.fingerprint = fingerprint
        existing.resolved_platforms = target_platforms
        existing.post = post
        existing.save()
    else:
        ProcessedLarkFile.objects.create(
            file_token=file_token,
            file_name=file_name,
            fingerprint=fingerprint,
            folder_token=folder["token"],
            folder_name=folder["name"],
            resolved_platforms=target_platforms,
            watch_config=config,
            post=post,
        )

    logger.info("Queued '%s' -> %s", file_name, ", ".join(target_platforms))
    return 1


def _create_post_for_file(
    workspace, file_path, file_name, caption, target_platforms,
    captions_by_platform: dict | None = None,
):
    """Create Post + MediaAsset + PlatformPosts scheduled for immediate publish."""
    from django.core.files import File

    from apps.composer.models import Post, PostMediaAttachment
    from apps.media_library.models import MediaAsset
    from apps.publisher.models import PlatformPost
    from apps.social_accounts.models import SocialAccount

    captions_by_platform = captions_by_platform or {}

    post = Post.objects.create(
        workspace=workspace,
        caption=caption,
        scheduled_at=timezone.now(),
    )

    ext = os.path.splitext(file_name)[1].lower()
    media_type = "video" if ext in {".mp4", ".mov", ".avi", ".mkv"} else "image"

    with open(file_path, "rb") as fh:
        asset = MediaAsset.objects.create(
            workspace=workspace,
            filename=file_name,
            media_type=media_type,
        )
        asset.file.save(file_name, File(fh), save=True)

    PostMediaAttachment.objects.create(post=post, media_asset=asset, position=0)

    for platform in target_platforms:
        platform_caption = captions_by_platform.get(platform, caption)
        for account in SocialAccount.objects.filter(
            workspace=workspace,
            platform=platform,
            connection_status="connected",
        ):
            PlatformPost.objects.create(
                post=post,
                social_account=account,
                scheduled_at=timezone.now(),
                status="scheduled",
                # Store per-platform AI caption in platform_extra
                platform_extra={"ai_caption": platform_caption},
            )

    return post
