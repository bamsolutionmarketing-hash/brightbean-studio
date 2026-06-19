"""Analytics views — workspace-scoped publish stats."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone


def _get_workspace(request, workspace_id):
    from apps.workspaces.models import Workspace
    return get_object_or_404(Workspace, id=workspace_id)


@login_required
def overview(request, workspace_id):
    workspace = _get_workspace(request, workspace_id)

    from apps.composer.models import PlatformPost

    now = timezone.now()
    days = int(request.GET.get("days", 30))
    since = now - timedelta(days=days)

    qs = PlatformPost.objects.filter(
        post__workspace=workspace,
        created_at__gte=since,
    ).select_related("social_account", "post")

    # ── Totals ──────────────────────────────────────────────────────────────
    total = qs.count()
    published = qs.filter(status="published").count()
    failed = qs.filter(status="failed").count()
    draft = qs.filter(status="draft").count()
    scheduled = qs.filter(status="scheduled").count()

    success_rate = round((published / total * 100) if total else 0, 1)

    # ── By platform ─────────────────────────────────────────────────────────
    by_platform = (
        qs.values("social_account__platform")
        .annotate(
            total=Count("id"),
            published=Count("id", filter=Q(status="published")),
            failed=Count("id", filter=Q(status="failed")),
        )
        .order_by("-published")
    )

    # ── Published per day (last `days` days) ─────────────────────────────
    from django.db.models.functions import TruncDate
    daily = (
        qs.filter(status="published")
        .annotate(day=TruncDate("published_at"))
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )
    daily_labels = [str(d["day"]) for d in daily]
    daily_counts = [d["count"] for d in daily]

    # ── Best hour to post (hour with most publishes) ──────────────────────
    from django.db.models.functions import ExtractHour
    hour_data = (
        qs.filter(status="published", published_at__isnull=False)
        .annotate(hour=ExtractHour("published_at"))
        .values("hour")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    best_hour = hour_data[0]["hour"] if hour_data else None
    hour_labels = [f"{h:02d}:00" for h in range(24)]
    hour_counts_map = {h["hour"]: h["count"] for h in hour_data}
    hour_counts = [hour_counts_map.get(h, 0) for h in range(24)]

    # ── Lark-sourced posts ────────────────────────────────────────────────
    lark_published = qs.filter(
        status="published",
        post__postmedia__media_asset__source="lark",
    ).distinct().count()

    # ── Recent failures ───────────────────────────────────────────────────
    recent_failures = (
        qs.filter(status="failed")
        .select_related("social_account", "post")
        .order_by("-updated_at")[:10]
    )

    ctx = {
        "workspace": workspace,
        "days": days,
        "total": total,
        "published": published,
        "failed": failed,
        "draft": draft,
        "scheduled": scheduled,
        "success_rate": success_rate,
        "by_platform": list(by_platform),
        "daily_labels": daily_labels,
        "daily_counts": daily_counts,
        "hour_labels": hour_labels,
        "hour_counts": hour_counts,
        "best_hour": best_hour,
        "lark_published": lark_published,
        "recent_failures": recent_failures,
    }
    return render(request, "analytics/overview.html", ctx)
