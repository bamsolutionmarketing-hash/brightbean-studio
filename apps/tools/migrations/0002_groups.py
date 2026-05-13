import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("workspaces", "0001_initial"),
        ("tools", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TeamToolGroup",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=120)),
                ("description", models.CharField(blank=True, default="", max_length=300)),
                ("icon_emoji", models.CharField(default="📁", max_length=8)),
                ("color", models.CharField(
                    choices=[("orange", "Orange"), ("pink", "Pink"), ("blue", "Blue"),
                             ("green", "Green"), ("purple", "Purple"), ("amber", "Amber"),
                             ("teal", "Teal"), ("stone", "Stone")],
                    default="orange", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="created_tool_groups",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("workspace", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="tool_groups",
                    to="workspaces.workspace",
                )),
            ],
            options={
                "ordering": ["name"],
                "unique_together": {("workspace", "name")},
            },
        ),
        migrations.CreateModel(
            name="TeamToolGroupAccess",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("granted_at", models.DateTimeField(auto_now_add=True)),
                ("granted_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="granted_tool_group_access",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("group", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="access_grants",
                    to="tools.teamtoolgroup",
                )),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="tool_group_grants",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"unique_together": {("group", "user")}},
        ),
        migrations.AddIndex(
            model_name="teamtoolgroup",
            index=models.Index(fields=["workspace"], name="tools_group_ws_idx"),
        ),
        migrations.AddIndex(
            model_name="teamtoolgroupaccess",
            index=models.Index(fields=["user"], name="tools_grant_user_idx"),
        ),
        migrations.AddField(
            model_name="teamtool",
            name="group",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="tools",
                to="tools.teamtoolgroup",
            ),
        ),
    ]
