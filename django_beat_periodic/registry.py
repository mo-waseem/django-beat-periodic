"""
Registry for periodic task metadata.

Each entry is collected by the ``@periodic_task`` decorator and later
consumed by :func:`django_beat_periodic.sync.sync_periodic_tasks`.
"""

PERIODIC_TASKS: list[dict] = []
