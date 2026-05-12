"""Models for tracking Lark Drive watch configs and processed files."""

from django.db import models


class LarkWatchConfig(models.Model):
    """A Lark Drive folder to watch for new media files."""

    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.CASCADE,
        related_name="lark_watch_configs",
    )
    folder_token = models.CharField(max_length=200)
    folder_name = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    poll_interval_seconds = models.IntegerField(default=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("workspace", "folder_token")]

    def __str__(self):
        return f"{self.workspace} -> {self.folder_name or self.folder_token}"


class ProcessedLarkFile(models.Model):
    """Tracks files already synced from Lark to prevent duplicate posts."""

    file_token = models.CharField(max_length=200, unique=True)
    file_name = models.CharField(max_length=500)
    fingerprint = models.CharField(max_length=64)
    folder_token = models.CharField(max_length=200)
    folder_name = models.CharField(max_length=200, blank=True)
    resolved_platforms = models.JSONField(default=list)
    watch_config = models.ForeignKey(
        LarkWatchConfig,
        on_delete=models.CASCADE,
        related_name="processed_files",
        null=True,
    )
    post = models.ForeignKey(
        "composer.Post",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lark_source",
    )
    processed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.file_name} ({', '.join(self.resolved_platforms)})"
