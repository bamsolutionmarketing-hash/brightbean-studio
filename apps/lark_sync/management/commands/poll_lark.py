"""Manually poll Lark Drive once and report what was processed.

Useful for testing the connection without waiting for the background worker:

    python manage.py poll_lark
    python manage.py poll_lark --list   # just list configs + connectivity check
"""

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Poll all active Lark watch folders once (synchronously)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--list",
            action="store_true",
            help="List watch configs and verify Lark credentials, without polling.",
        )

    def handle(self, *args, **options):
        from apps.lark_sync.models import LarkWatchConfig
        from apps.lark_sync.tasks import _poll_lark_folder

        app_id = getattr(settings, "LARK_APP_ID", "")
        app_secret = getattr(settings, "LARK_APP_SECRET", "")

        if not app_id or not app_secret:
            self.stderr.write(self.style.ERROR(
                "LARK_APP_ID / LARK_APP_SECRET are not set. Add them to your .env."
            ))
            return

        # Connectivity check
        from providers.lark import LarkClient
        client = LarkClient(app_id, app_secret, use_feishu=getattr(settings, "LARK_USE_FEISHU", False))
        try:
            client._get_tenant_token()
            self.stdout.write(self.style.SUCCESS("✓ Lark credentials OK (got tenant token)"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"✗ Lark auth failed: {e}"))
            return

        configs = LarkWatchConfig.objects.filter(is_active=True).select_related("workspace")
        if not configs:
            self.stdout.write(self.style.WARNING(
                "No active LarkWatchConfig found. Add one in /admin/lark_sync/larkwatchconfig/."
            ))
            return

        self.stdout.write(f"Found {configs.count()} active watch config(s):")
        for c in configs:
            self.stdout.write(f"  • {c.workspace} → {c.folder_name or c.folder_token}")

        if options["list"]:
            return

        total = 0
        for config in configs:
            try:
                processed = _poll_lark_folder(config)
                total += processed
                self.stdout.write(self.style.SUCCESS(
                    f"  processed {processed} new/changed file(s) from {config.folder_name or config.folder_token}"
                ))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  error polling {config.folder_token}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"Done. {total} file(s) queued for publishing."))
