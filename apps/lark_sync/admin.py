from django.contrib import admin

from .models import LarkWatchConfig, ProcessedLarkFile


@admin.register(LarkWatchConfig)
class LarkWatchConfigAdmin(admin.ModelAdmin):
    list_display = ("workspace", "folder_name", "folder_token", "is_active", "poll_interval_seconds", "created_at")
    list_filter = ("is_active",)
    search_fields = ("folder_name", "folder_token", "workspace__name")
    autocomplete_fields = ("workspace",)
    fieldsets = (
        (None, {
            "fields": ("workspace", "folder_token", "folder_name", "is_active"),
        }),
        ("Polling", {
            "fields": ("poll_interval_seconds",),
            "description": "How the watcher behaves. The folder_token is the part "
                           "after /folder/ in the Lark Drive URL.",
        }),
    )


@admin.register(ProcessedLarkFile)
class ProcessedLarkFileAdmin(admin.ModelAdmin):
    list_display = ("file_name", "folder_name", "_platforms", "post", "processed_at")
    list_filter = ("folder_name", "processed_at")
    search_fields = ("file_name", "file_token")
    readonly_fields = (
        "file_token", "file_name", "fingerprint", "folder_token", "folder_name",
        "resolved_platforms", "watch_config", "post", "telegram_storage",
        "processed_at", "created_at",
    )

    @admin.display(description="Platforms")
    def _platforms(self, obj):
        return ", ".join(obj.resolved_platforms or [])

    def has_add_permission(self, request):
        return False
