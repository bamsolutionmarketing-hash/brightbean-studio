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

from .models import (
    PLATFORM_PRESETS,
    PRESET_BY_KEY,
    TeamTool,
    TeamToolGroup,
    TeamToolGroupAccess,
    TeamToolUsageLog,
)

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
def _user_can_manage(request) -> bool:
    return bool(
        request.workspace_membership
        and request.workspace_membership.effective_permissions.get("manage_workspace_settings", False)
    )


def _visible_tool_ids(request, workspace_id) -> set:
    """Return the set of TeamTool ids the current user is allowed to see.

    Admins see everything. Members see:
      - All tools without a group (public)
      - All tools in groups they have explicit access to
    """
    if _user_can_manage(request):
        return set(
            TeamTool.objects
            .filter(workspace_id=workspace_id, is_active=True)
            .values_list("id", flat=True)
        )

    public_ids = TeamTool.objects.filter(
        workspace_id=workspace_id, is_active=True, group__isnull=True,
    ).values_list("id", flat=True)

    allowed_group_ids = TeamToolGroupAccess.objects.filter(
        user=request.user, group__workspace_id=workspace_id,
    ).values_list("group_id", flat=True)

    group_tool_ids = TeamTool.objects.filter(
        workspace_id=workspace_id, is_active=True, group_id__in=allowed_group_ids,
    ).values_list("id", flat=True)

    return set(public_ids) | set(group_tool_ids)


@login_required
def tool_list(request, workspace_id):
    can_manage = _user_can_manage(request)
    visible_ids = _visible_tool_ids(request, workspace_id)

    tools = (
        TeamTool.objects
        .filter(id__in=visible_ids)
        .select_related("current_user", "group")
        .order_by("group__name", "name")
    )

    # Bucket tools into sections: each visible group + a "public" section.
    if can_manage:
        groups = list(TeamToolGroup.objects.filter(workspace_id=workspace_id).order_by("name"))
    else:
        allowed = TeamToolGroupAccess.objects.filter(
            user=request.user, group__workspace_id=workspace_id,
        ).values_list("group_id", flat=True)
        groups = list(TeamToolGroup.objects.filter(id__in=allowed).order_by("name"))

    sections = []
    for g in groups:
        section_tools = [t for t in tools if t.group_id == g.id]
        sections.append({"group": g, "tools": section_tools})
    public_tools = [t for t in tools if t.group_id is None]

    return render(request, "tools/list.html", {
        "workspace_id": workspace_id,
        "sections": sections,
        "public_tools": public_tools,
        "all_groups": groups,
        "presets": PLATFORM_PRESETS,
        "can_manage": can_manage,
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

    group_id = (request.POST.get("group_id") or "").strip()
    group = None
    if group_id:
        group = TeamToolGroup.objects.filter(id=group_id, workspace_id=workspace_id).first()

    TeamTool.objects.create(
        workspace_id=workspace_id,
        group=group,
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

    # Group-based access check: admins bypass; members need group access or public tool.
    if not _user_can_manage(request) and tool.group_id is not None:
        has_access = TeamToolGroupAccess.objects.filter(
            group_id=tool.group_id, user=request.user,
        ).exists()
        if not has_access:
            return JsonResponse(
                {"ok": False, "error": "Bạn không có quyền dùng tool này."},
                status=403,
            )

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


# ------------------------------------------------------------------
# Groups: list / create / edit / delete (admin)
# ------------------------------------------------------------------
@login_required
@require_permission("manage_workspace_settings")
def group_list(request, workspace_id):
    groups = (
        TeamToolGroup.objects
        .filter(workspace_id=workspace_id)
        .prefetch_related("tools", "access_grants__user")
        .order_by("name")
    )
    return render(request, "tools/groups.html", {
        "workspace_id": workspace_id,
        "groups": groups,
    })


@login_required
@require_permission("manage_workspace_settings")
@require_POST
def group_create(request, workspace_id):
    name = (request.POST.get("name") or "").strip()
    icon_emoji = (request.POST.get("icon_emoji") or "📁").strip()[:8]
    color = (request.POST.get("color") or "orange").strip()
    description = (request.POST.get("description") or "").strip()[:300]

    if not name:
        messages.error(request, "Tên group là bắt buộc.")
        return redirect("tools:group_list", workspace_id=workspace_id)

    if TeamToolGroup.objects.filter(workspace_id=workspace_id, name=name).exists():
        messages.error(request, f"Group '{name}' đã tồn tại.")
        return redirect("tools:group_list", workspace_id=workspace_id)

    group = TeamToolGroup.objects.create(
        workspace_id=workspace_id,
        name=name,
        icon_emoji=icon_emoji,
        color=color,
        description=description,
        created_by=request.user,
    )
    messages.success(request, f"Đã tạo group '{name}'.")
    return redirect("tools:group_manage", workspace_id=workspace_id, group_id=group.id)


@login_required
@require_permission("manage_workspace_settings")
def group_manage(request, workspace_id, group_id):
    from apps.members.models import WorkspaceMembership

    group = get_object_or_404(TeamToolGroup, id=group_id, workspace_id=workspace_id)

    # Tools currently in this group + tools without a group (candidates to add)
    tools_in_group = group.tools.filter(is_active=True).order_by("name")
    candidate_tools = TeamTool.objects.filter(
        workspace_id=workspace_id, is_active=True,
    ).exclude(group=group).order_by("name")

    # Users in workspace + which already have access
    memberships = (
        WorkspaceMembership.objects
        .filter(workspace_id=workspace_id, workspace__is_archived=False)
        .select_related("user")
    )
    granted_user_ids = set(
        group.access_grants.values_list("user_id", flat=True)
    )
    members_with_access = [m for m in memberships if m.user_id in granted_user_ids]
    members_without_access = [m for m in memberships if m.user_id not in granted_user_ids]

    return render(request, "tools/group_manage.html", {
        "workspace_id": workspace_id,
        "group": group,
        "tools_in_group": tools_in_group,
        "candidate_tools": candidate_tools,
        "members_with_access": members_with_access,
        "members_without_access": members_without_access,
    })


@login_required
@require_permission("manage_workspace_settings")
@require_POST
def group_edit(request, workspace_id, group_id):
    group = get_object_or_404(TeamToolGroup, id=group_id, workspace_id=workspace_id)
    name = (request.POST.get("name") or "").strip()
    if name:
        group.name = name
    group.description = (request.POST.get("description") or "").strip()[:300]
    group.icon_emoji = (request.POST.get("icon_emoji") or group.icon_emoji)[:8]
    group.color = (request.POST.get("color") or group.color).strip()
    group.save()
    messages.success(request, "Đã lưu thay đổi.")
    return redirect("tools:group_manage", workspace_id=workspace_id, group_id=group.id)


@login_required
@require_permission("manage_workspace_settings")
@require_POST
def group_delete(request, workspace_id, group_id):
    group = get_object_or_404(TeamToolGroup, id=group_id, workspace_id=workspace_id)
    # Tools in this group revert to public (group set to NULL by SET_NULL).
    group_name = group.name
    group.delete()
    messages.success(request, f"Đã xoá group '{group_name}'. Các tools bên trong trở thành public.")
    return redirect("tools:group_list", workspace_id=workspace_id)


@login_required
@require_permission("manage_workspace_settings")
@require_POST
def group_grant(request, workspace_id, group_id):
    group = get_object_or_404(TeamToolGroup, id=group_id, workspace_id=workspace_id)
    user_id = (request.POST.get("user_id") or "").strip()
    if not user_id:
        return redirect("tools:group_manage", workspace_id=workspace_id, group_id=group.id)

    TeamToolGroupAccess.objects.get_or_create(
        group=group, user_id=user_id,
        defaults={"granted_by": request.user},
    )
    return redirect("tools:group_manage", workspace_id=workspace_id, group_id=group.id)


@login_required
@require_permission("manage_workspace_settings")
@require_POST
def group_revoke(request, workspace_id, group_id):
    group = get_object_or_404(TeamToolGroup, id=group_id, workspace_id=workspace_id)
    user_id = (request.POST.get("user_id") or "").strip()
    if user_id:
        TeamToolGroupAccess.objects.filter(group=group, user_id=user_id).delete()
    return redirect("tools:group_manage", workspace_id=workspace_id, group_id=group.id)


@login_required
@require_permission("manage_workspace_settings")
@require_POST
def tool_assign_group(request, workspace_id, tool_id):
    """Move a tool into a group, or remove it (set group_id=''). """
    tool = _get_tool(workspace_id, tool_id)
    group_id = (request.POST.get("group_id") or "").strip()
    if group_id:
        group = get_object_or_404(TeamToolGroup, id=group_id, workspace_id=workspace_id)
        tool.group = group
    else:
        tool.group = None
    tool.save(update_fields=["group", "updated_at"])
    redirect_to = request.POST.get("redirect_to") or "tools:list"
    if redirect_to == "tools:group_manage" and tool.group_id:
        return redirect("tools:group_manage", workspace_id=workspace_id, group_id=tool.group_id)
    return redirect("tools:list", workspace_id=workspace_id)
