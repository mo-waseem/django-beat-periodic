from __future__ import annotations

from celery import current_app

from django_beat_periodic.registry import PERIODIC_TASKS


def periodic_task(
    interval: int | None = None,
    crontab: str | dict | None = None,
    enabled: bool = True,
    **kwargs,
):
    """Decorator that marks a function as a periodic Celery task.

    The function is automatically wrapped with ``@app.task`` and its
    schedule metadata is stored in :data:`PERIODIC_TASKS` so that
    :func:`~django_beat_periodic.sync.sync_periodic_tasks` can
    create the corresponding ``django_celery_beat`` database rows at
    startup time.

    Args:
        interval: Run frequency.  Either an ``int`` (seconds) or a
            :class:`~datetime.timedelta`.
        crontab: Cron expression as a 5-part string (``"*/5 * * * *"``)
            or a ``dict`` of :class:`~django_celery_beat.models.CrontabSchedule`
            field values.
        enabled: Whether the periodic task should be enabled (default ``True``).
        **kwargs: Extra fields forwarded to
            :class:`~django_celery_beat.models.PeriodicTask` (e.g. ``name``,
            ``queue``, ``priority``, ``args``, ``kwargs``).
    """

    def decorator(func):
        PERIODIC_TASKS.append(
            {
                "func": func,
                "interval": interval,
                "crontab": crontab,
                "enabled": enabled,
                "kwargs": kwargs,
            }
        )
        # Wrap with the standard Celery task decorator using the
        # project's current Celery application.
        return current_app.task(func)

    return decorator
