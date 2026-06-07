import sys

from django.apps import AppConfig


SKIP_STARTUP_SYNC_COMMANDS = {
    "disable_periodic_task",
    "enable_periodic_task",
    "list_periodic_tasks",
}


class DjangoBeatPeriodicConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_beat_periodic"
    verbose_name = "Django Beat Periodic"

    def ready(self):
        if self._should_skip_startup_sync():
            return

        from django_beat_periodic.sync import sync_periodic_tasks

        sync_periodic_tasks()

    @staticmethod
    def _should_skip_startup_sync() -> bool:
        return len(sys.argv) > 1 and sys.argv[1] in SKIP_STARTUP_SYNC_COMMANDS
