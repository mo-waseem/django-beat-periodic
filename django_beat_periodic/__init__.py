"""django-beat-periodic — auto-sync @periodic_task decorators to django-celery-beat."""

__version__ = "0.5.0"

from django_beat_periodic.decorators import periodic_task
from django_beat_periodic.sync import sync_periodic_tasks

__all__ = ["periodic_task", "sync_periodic_tasks"]
