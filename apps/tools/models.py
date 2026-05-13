"""Shared-account tools (Canva, ChatGPT, etc.) for a workspace.

Cookies are stored encrypted at rest and never exposed to the client.
Members can launch a hardened browser session against any tool, then
must "return" it before another member can use it.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from apps.common.encryption import EncryptedTextField


PLATFORM_PRESETS = [
    {"key": "canva",    "name": "Canva",    "url": "https://www.canva.com",       "icon_emoji": "🎨"},
    {"key": "magnific", "name": "Magnific", "url": "https://magnific.ai",         "icon_emoji": "✨"},
    {"key": "chatgpt",  "name": "ChatGPT",  "url": "https://chatgpt.com",         "icon_emoji": "💬"},
    {"key": "grok",     "name": "Grok",     "url": "https://grok.com",            "icon_emoji": "🤖"},
    {"key": "gemini",   "name": "Gemini",   "url": "https://gemini.google.com",   "icon_emoji": "♊"},
    {"key": "custom",   "name": "Custom",   "url": "",                            "icon_emoji": "🔗"},
]
PRESET_BY_KEY = {p["key"]: p for p in PLATFORM_PRESETS}


class TeamTool(models.Model):
    """A shared third-party account (cookies stored encrypted)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.CASCADE,
        related_name="team_tools",
    )
    name = models.CharField(max_length=120)
    platform_key = models.CharField(max_length=40, default="custom")
    url = models.URLField(max_length=500)
    icon_url = models.URLField(max_length=500, blank=True, default="")
    description = models.CharField(max_length=300, blank=True, default="")

    # Encrypted at rest — never returned to clients.
    cookies_json = EncryptedTextField()

    is_active = models.BooleanField(default=True)

    # In-use state
    current_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="active_team_tools",
    )
    session_started_at = models.DateTimeField(null=True, blank=True)
    session_temp_dir = models.CharField(max_length=500, blank=True, default="")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="created_team_tools",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["workspace", "is_active"])]

    def __str__(self):
        return f"{self.name} ({self.platform_key})"

    @property
    def is_in_use(self) -> bool:
        return self.current_user_id is not None

    @property
    def icon_emoji(self) -> str:
        preset = PRESET_BY_KEY.get(self.platform_key)
        return preset["icon_emoji"] if preset else "🔗"


class TeamToolUsageLog(models.Model):
    """Immutable audit trail — one row per launch."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tool = models.ForeignKey(TeamTool, on_delete=models.CASCADE, related_name="usage_logs")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="team_tool_usage_logs",
    )
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.CASCADE,
        related_name="team_tool_usage_logs",
    )

    started_at = models.DateTimeField(auto_now_add=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True, default="")

    forced_return = models.BooleanField(default=False)
    notes = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["workspace", "-started_at"]),
            models.Index(fields=["tool", "-started_at"]),
        ]

    def __str__(self):
        return f"{self.user} → {self.tool} @ {self.started_at:%Y-%m-%d %H:%M}"
