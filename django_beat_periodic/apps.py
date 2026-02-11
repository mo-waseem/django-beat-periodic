from django.apps import AppConfig


class DjangoBeatPeriodicConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_beat_periodic"
    verbose_name = "Django Beat Periodic"

    def ready(self):
        from django_beat_periodic.sync import sync_periodic_tasks

        sync_periodic_tasks()
