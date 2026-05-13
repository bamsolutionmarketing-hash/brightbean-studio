from django.contrib import admin

from .models import TeamTool, TeamToolUsageLog


@admin.register(TeamTool)
class TeamToolAdmin(admin.ModelAdmin):
    list_display = ("name", "platform_key", "workspace", "is_active", "current_user", "updated_at")
    list_filter = ("platform_key", "is_active")
    search_fields = ("name", "url")
    readonly_fields = ("created_at", "updated_at", "session_started_at")


@admin.register(TeamToolUsageLog)
class TeamToolUsageLogAdmin(admin.ModelAdmin):
    list_display = ("user", "tool", "workspace", "started_at", "returned_at", "duration_seconds", "forced_return")
    list_filter = ("forced_return", "started_at")
    search_fields = ("user__email", "tool__name")
    readonly_fields = tuple(f.name for f in TeamToolUsageLog._meta.fields)
