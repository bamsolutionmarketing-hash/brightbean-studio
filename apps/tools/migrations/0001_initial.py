import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.common.encryption


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("workspaces", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TeamTool",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=120)),
                ("platform_key", models.CharField(default="custom", max_length=40)),
                ("url", models.URLField(max_length=500)),
                ("icon_url", models.URLField(blank=True, default="", max_length=500)),
                ("description", models.CharField(blank=True, default="", max_length=300)),
                ("cookies_json", apps.common.encryption.EncryptedTextField()),
                ("is_active", models.BooleanField(default=True)),
                ("session_started_at", models.DateTimeField(blank=True, null=True)),
                ("session_temp_dir", models.CharField(blank=True, default="", max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="created_team_tools",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("current_user", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="active_team_tools",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("workspace", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="team_tools",
                    to="workspaces.workspace",
                )),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="TeamToolUsageLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("returned_at", models.DateTimeField(blank=True, null=True)),
                ("duration_seconds", models.IntegerField(blank=True, null=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, default="", max_length=500)),
                ("forced_return", models.BooleanField(default=False)),
                ("notes", models.CharField(blank=True, default="", max_length=300)),
                ("tool", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="usage_logs",
                    to="tools.teamtool",
                )),
                ("user", models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="team_tool_usage_logs",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("workspace", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="team_tool_usage_logs",
                    to="workspaces.workspace",
                )),
            ],
            options={"ordering": ["-started_at"]},
        ),
        migrations.AddIndex(
            model_name="teamtool",
            index=models.Index(fields=["workspace", "is_active"], name="tools_teamt_workspa_idx"),
        ),
        migrations.AddIndex(
            model_name="teamtoolusagelog",
            index=models.Index(fields=["workspace", "-started_at"], name="tools_tealog_ws_idx"),
        ),
        migrations.AddIndex(
            model_name="teamtoolusagelog",
            index=models.Index(fields=["tool", "-started_at"], name="tools_tealog_tool_idx"),
        ),
    ]
