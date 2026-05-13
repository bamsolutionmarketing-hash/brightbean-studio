"""Background tasks: auto-release tools that haven't been returned."""

from __future__ import annotations

import logging
from datetime import timedelta

from background_task import background
from django.utils import timezone

logger = logging.getLogger(__name__)

# Auto-return after this many minutes if user forgets to return.
AUTO_RETURN_AFTER_MINUTES = 120


@background(schedule=0)
def auto_return_stale_tools():
    """Release tools whose session is older than AUTO_RETURN_AFTER_MINUTES."""
    from .models import TeamTool
    from .views import _release_tool

    threshold = timezone.now() - timedelta(minutes=AUTO_RETURN_AFTER_MINUTES)
    stale = TeamTool.objects.filter(
        current_user__isnull=False,
        session_started_at__lt=threshold,
    )

    count = 0
    for tool in stale:
        try:
            _release_tool(
                tool,
                forced=True,
                notes=f"Auto-returned after {AUTO_RETURN_AFTER_MINUTES} min timeout",
            )
            count += 1
        except Exception:
            logger.exception("Failed to auto-return tool %s", tool.id)

    if count:
        logger.info("Auto-returned %d stale tool sessions", count)
    return count
