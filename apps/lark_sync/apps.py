import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class LarkSyncConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.lark_sync"
    verbose_name = "Lark Sync"

    def ready(self):
        from django.db.models.signals import post_migrate

        post_migrate.connect(self._register_poll_task, sender=self)

    @staticmethod
    def _register_poll_task(sender, **kwargs):
        """Register the recurring Lark-poll task after migrations are applied.

        Only registers when LARK_APP_ID/SECRET are configured so installs that
        don't use Lark don't get a no-op task churning every few minutes.
        """
        try:
            from django.conf import settings

            if not getattr(settings, "LARK_APP_ID", "") or not getattr(settings, "LARK_APP_SECRET", ""):
                logger.debug("Lark not configured — skipping poll task registration")
                return

            from background_task.models import Task

            from apps.lark_sync.tasks import poll_all_lark_folders

            interval = int(getattr(settings, "LARK_POLL_INTERVAL", 300))
            if not Task.objects.filter(verbose_name="poll_all_lark_folders").exists():
                poll_all_lark_folders(
                    repeat=interval,
                    verbose_name="poll_all_lark_folders",
                )
                logger.info("Registered recurring Lark poll task (every %ds)", interval)
        except Exception:
            logger.debug("Skipping Lark poll task registration (database not ready)")
