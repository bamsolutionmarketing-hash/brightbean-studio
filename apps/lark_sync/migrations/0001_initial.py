from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("workspaces", "0001_initial"),
        ("composer", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="LarkWatchConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("folder_token", models.CharField(max_length=200)),
                ("folder_name", models.CharField(blank=True, max_length=200)),
                ("is_active", models.BooleanField(default=True)),
                ("poll_interval_seconds", models.IntegerField(default=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("workspace", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="lark_watch_configs",
                    to="workspaces.workspace",
                )),
            ],
            options={"unique_together": {("workspace", "folder_token")}},
        ),
        migrations.CreateModel(
            name="ProcessedLarkFile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("file_token", models.CharField(max_length=200, unique=True)),
                ("file_name", models.CharField(max_length=500)),
                ("fingerprint", models.CharField(max_length=64)),
                ("folder_token", models.CharField(max_length=200)),
                ("folder_name", models.CharField(blank=True, max_length=200)),
                ("resolved_platforms", models.JSONField(default=list)),
                ("processed_at", models.DateTimeField(auto_now_add=True)),
                ("watch_config", models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="processed_files",
                    to="apps_lark_sync.larkwatchconfig",
                )),
                ("post", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="lark_source",
                    to="composer.post",
                )),
            ],
        ),
    ]
