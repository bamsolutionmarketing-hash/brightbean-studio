"""Team Tools views: list / upload / launch / return / history."""

from __future__ import annotations

import logging
import threading

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.members.decorators import require_permission

from .models import PLATFORM_PRESETS, PRESET_BY_KEY, TeamTool, TeamToolUsageLog

logger = logging.getLogger(__name__)


def _client_ip(request) -> str | None:
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _get_tool(workspace_id, tool_id) -> TeamTool:
    return get_object_or_404(TeamTool, id=tool_id, workspace_id=workspace_id)


# ------------------------------------------------------------------
# List (any workspace member)
# ------------------------------------------------------------------
@login_required
def tool_list(request, workspace_id):
    tools = (
        TeamTool.objects
        .filter(workspace_id=workspace_id, is_active=True)
        .select_related("current_user")
        .order_by("name")
    )
    can_manage = (
        request.workspace_membership
        and request.workspace_membership.effective_permissions.get("manage_workspace_settings", False)
    )
    return render(request, "tools/list.html", {
        "workspace_id": workspace_id,
        "tools": tools,
        "presets": PLATFORM_PRESETS,
        "can_manage": bool(can_manage),
        "now": timezone.now(),
    })


# ------------------------------------------------------------------
# Upload (admin)
# ------------------------------------------------------------------
@login_required
@require_permission("manage_workspace_settings")
@require_POST
@ratelimit(key="user", rate="20/m", method="POST", block=True)
def tool_upload(request, workspace_id):
    name = (request.POST.get("name") or "").strip()
    platform_key = (request.POST.get("platform_key") or "custom").strip()
    url = (request.POST.get("url") or "").strip()
    description = (request.POST.get("description") or "").strip()[:300]
    cookies_payload = (request.POST.get("cookies_json") or "").strip()

    preset = PRESET_BY_KEY.get(platform_key)
    if preset and not url:
        url = preset["url"]
    if preset and not name:
        name = preset["name"]

    if not name or not url or not cookies_payload:
        messages.error(request, "Name, URL and cookies JSON are required.")
        return redirect("tools:list", workspace_id=workspace_id)

    # Validate cookies parse before saving
    from providers.cookie_import import _parse_payload, _normalize_cookie
    try:
        raw = _parse_payload(cookies_payload)
        normalized = [c for c in (_normalize_cookie(rc) for rc in raw) if c]
        if not normalized:
            raise ValueError("No valid cookies")
    except Exception as exc:
        messages.error(request, f"Invalid cookies JSON: {exc}")
        return redirect("tools:list", workspace_id=workspace_id)

    TeamTool.objects.create(
        workspace_id=workspace_id,
        name=name,
        platform_key=platform_key,
        url=url,
        description=description,
        cookies_json=cookies_payload,
        created_by=request.user,
    )
    messages.success(request, f"Tool '{name}' added with {len(normalized)} cookies.")
    return redirect("tools:list", workspace_id=workspace_id)


# ------------------------------------------------------------------
# Edit cookies (admin)
# ------------------------------------------------------------------
@login_required
@require_permission("manage_workspace_settings")
@require_POST
def tool_update_cookies(request, workspace_id, tool_id):
    tool = _get_tool(workspace_id, tool_id)
    payload = (request.POST.get("cookies_json") or "").strip()
    if not payload:
        messages.error(request, "Cookies JSON is required.")
        return redirect("tools:list", workspace_id=workspace_id)

    from providers.cookie_import import _parse_payload, _normalize_cookie
    try:
        raw = _parse_payload(payload)
        normalized = [c for c in (_normalize_cookie(rc) for rc in raw) if c]
        if not normalized:
            raise ValueError("No valid cookies")
    except Exception as exc:
        messages.error(request, f"Invalid cookies JSON: {exc}")
        return redirect("tools:list", workspace_id=workspace_id)

    tool.cookies_json = payload
    tool.save(update_fields=["cookies_json", "updated_at"])
    messages.success(request, f"Cookies refreshed for {tool.name}.")
    return redirect("tools:list", workspace_id=workspace_id)


# ------------------------------------------------------------------
# Delete (admin)
# ------------------------------------------------------------------
@login_required
@require_permission("manage_workspace_settings")
@require_POST
def tool_delete(request, workspace_id, tool_id):
    tool = _get_tool(workspace_id, tool_id)
    tool.delete()
    messages.success(request, f"Tool '{tool.name}' deleted.")
    return redirect("tools:list", workspace_id=workspace_id)


# ------------------------------------------------------------------
# Launch (any member)
# ------------------------------------------------------------------
@login_required
@require_POST
@ratelimit(key="user", rate="10/m", method="POST", block=True)
def tool_launch(request, workspace_id, tool_id):
    if not request.workspace_membership:
        raise PermissionDenied("Not a workspace member.")

    tool = _get_tool(workspace_id, tool_id)

    if tool.is_in_use and tool.current_user_id != request.user.id:
        return JsonResponse(
            {"ok": False, "error": f"In use by {tool.current_user.name or tool.current_user.email}"},
            status=409,
        )

    log = TeamToolUsageLog.objects.create(
        tool=tool,
        user=request.user,
        workspace_id=workspace_id,
        ip_address=_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
    )

    cookies = tool.cookies_json
    tool_url = tool.url

    def _run():
        from providers.hardened_browser import launch_tool_session
        try:
            launch_tool_session(tool_url, cookies)
        except Exception:
            logger.exception("Hardened browser session failed for tool %s", tool.id)
        finally:
            _auto_finish_log(log.id, forced=False, notes="Browser window closed")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    tool.current_user = request.user
    tool.session_started_at = timezone.now()
    tool.save(update_fields=["current_user", "session_started_at", "updated_at"])

    return JsonResponse({
        "ok": True,
        "log_id": str(log.id),
        "message": "Đang mở trình duyệt khoá an toàn — đóng cửa sổ khi dùng xong, hoặc bấm 'Trả tài khoản'.",
    })


# ------------------------------------------------------------------
# Return (only current user) — closes session, shreds profile
# ------------------------------------------------------------------
@login_required
@require_POST
def tool_return(request, workspace_id, tool_id):
    tool = _get_tool(workspace_id, tool_id)
    if tool.current_user_id != request.user.id:
        return JsonResponse({"ok": False, "error": "You are not currently using this tool."}, status=403)

    _release_tool(tool, forced=False, notes="Returned by user")
    return JsonResponse({"ok": True})


# ------------------------------------------------------------------
# Force-return (admin)
# ------------------------------------------------------------------
@login_required
@require_permission("manage_workspace_settings")
@require_POST
def tool_force_return(request, workspace_id, tool_id):
    tool = _get_tool(workspace_id, tool_id)
    if not tool.is_in_use:
        return JsonResponse({"ok": False, "error": "Tool is not in use."}, status=400)

    _release_tool(tool, forced=True, notes=f"Force-returned by {request.user}")
    return JsonResponse({"ok": True})


# ------------------------------------------------------------------
# Usage history (admin)
# ------------------------------------------------------------------
@login_required
@require_permission("manage_workspace_settings")
def tool_history(request, workspace_id):
    logs = (
        TeamToolUsageLog.objects
        .filter(workspace_id=workspace_id)
        .select_related("tool", "user")
        .order_by("-started_at")[:200]
    )
    return render(request, "tools/history.html", {
        "workspace_id": workspace_id,
        "logs": logs,
    })


# ------------------------------------------------------------------
# Internals
# ------------------------------------------------------------------
def _release_tool(tool: TeamTool, *, forced: bool, notes: str) -> None:
    """Clear the in-use state and close the most recent open log."""
    log = (
        TeamToolUsageLog.objects
        .filter(tool=tool, returned_at__isnull=True)
        .order_by("-started_at")
        .first()
    )
    if log:
        _auto_finish_log(log.id, forced=forced, notes=notes)

    tool.current_user = None
    tool.session_started_at = None
    tool.session_temp_dir = ""
    tool.save(update_fields=["current_user", "session_started_at", "session_temp_dir", "updated_at"])


def _auto_finish_log(log_id, *, forced: bool, notes: str) -> None:
    try:
        log = TeamToolUsageLog.objects.get(id=log_id, returned_at__isnull=True)
    except TeamToolUsageLog.DoesNotExist:
        return
    now = timezone.now()
    log.returned_at = now
    log.duration_seconds = int((now - log.started_at).total_seconds())
    log.forced_return = forced
    log.notes = (log.notes + " " + notes).strip()[:300]
    log.save(update_fields=["returned_at", "duration_seconds", "forced_return", "notes"])
