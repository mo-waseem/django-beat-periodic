from __future__ import annotations

import json
import logging
from datetime import timedelta

from django.utils import timezone

from django_beat_periodic.registry import PERIODIC_TASKS

logger = logging.getLogger("django_beat_periodic")

# Marker used in PeriodicTask.description to identify tasks managed by this
# package.  Only rows carrying this marker will be auto-deleted when the
# corresponding @periodic_task decorator is removed from the code.
MANAGED_DESCRIPTION = "Managed by django-beat-periodic"

# Guard against duplicate syncs in dev (auto-reload runs ready() twice).
_already_synced = False


def sync_periodic_tasks() -> None:
    """Synchronise decorator-registered periodic tasks with the database.

    For every entry in :data:`~django_beat_periodic.registry.PERIODIC_TASKS`
    this function creates or updates the corresponding
    :class:`~django_celery_beat.models.PeriodicTask` row (together with its
    :class:`~django_celery_beat.models.IntervalSchedule` or
    :class:`~django_celery_beat.models.CrontabSchedule`).

    The function is idempotent: it skips DB writes when nothing changed and
    only calls ``PeriodicTasks.update_changed()`` when at least one row was
    created or modified.
    """
    global _already_synced
    if _already_synced:
        return
    _already_synced = True

    from django_celery_beat.models import (
        CrontabSchedule,
        IntervalSchedule,
        PeriodicTask,
        PeriodicTasks,
    )

    # The tables may not exist yet (before first migration or during test
    # collection).  Silently skip in that case.
    try:
        PeriodicTask.objects.count()
    except Exception:
        _already_synced = False
        logger.debug("django_celery_beat tables do not exist yet — skipping sync.")
        return

    logger.info("Synchronizing periodic tasks with the database...")

    active_task_names: list[str] = []
    changed_count = 0

    for task_info in PERIODIC_TASKS:
        func = task_info["func"]
        interval = task_info["interval"]
        crontab = task_info["crontab"]
        enabled = task_info["enabled"]
        kwargs = task_info["kwargs"].copy()

        task_path = f"{func.__module__}.{func.__name__}"
        task_name = kwargs.pop("name", task_path)
        active_task_names.append(task_name)

        # ----------------------------------------------------------
        # Build the schedule
        # ----------------------------------------------------------
        schedule_kwargs: dict = {
            "interval": None,
            "crontab": None,
            "solar": None,
            "clocked": None,
        }

        if interval is not None:
            if isinstance(interval, int):
                interval = timedelta(seconds=interval)
            schedule, _ = IntervalSchedule.objects.get_or_create(
                every=int(interval.total_seconds()),
                period=IntervalSchedule.SECONDS,
            )
            schedule_kwargs["interval"] = schedule

        elif crontab is not None:
            if isinstance(crontab, str):
                parts = crontab.split()
                if len(parts) == 5:
                    schedule, _ = CrontabSchedule.objects.get_or_create(
                        minute=parts[0],
                        hour=parts[1],
                        day_of_month=parts[2],
                        month_of_year=parts[3],
                        day_of_week=parts[4],
                    )
                    schedule_kwargs["crontab"] = schedule
                else:
                    logger.warning(
                        "Invalid crontab string for %s: '%s' "
                        "(expected 5 space-separated fields)",
                        task_path,
                        crontab,
                    )
                    continue
            elif isinstance(crontab, dict):
                schedule, _ = CrontabSchedule.objects.get_or_create(**crontab)
                schedule_kwargs["crontab"] = schedule

        if not (interval or crontab):
            logger.warning("Task %s has no schedule defined — skipping.", task_path)
            continue

        # ----------------------------------------------------------
        # Build the PeriodicTask defaults
        # ----------------------------------------------------------
        # Get start_time from kwargs or default to now
        start_time = kwargs.pop("start_time", timezone.now())

        defaults = {
            "task": task_path,
            "enabled": enabled,
            "description": MANAGED_DESCRIPTION,
            "args": json.dumps(kwargs.pop("args", [])),
            "kwargs": json.dumps(kwargs.pop("kwargs", {})),
            "queue": kwargs.pop("queue", None),
            "priority": kwargs.pop("priority", None),
            "start_time": start_time,
            **schedule_kwargs,
            **kwargs,
        }

        # ----------------------------------------------------------
        # Create or update
        # ----------------------------------------------------------
        obj, created = PeriodicTask.objects.get_or_create(
            name=task_name, defaults=defaults
        )
        if not created:
            needs_update = False
            for key, value in defaults.items():
                # Avoid resetting start_time if it's already set to a non-null value
                if key == "start_time" and obj.start_time is not None:
                    continue
                if getattr(obj, key) != value:
                    setattr(obj, key, value)
                    needs_update = True
            if needs_update:
                obj.save()
                changed_count += 1
        else:
            changed_count += 1

    # ----------------------------------------------------------
    # Remove stale tasks (decorator removed from code)
    # ----------------------------------------------------------
    stale_tasks = PeriodicTask.objects.filter(
        description=MANAGED_DESCRIPTION,
    ).exclude(name__in=active_task_names)

    stale_count = stale_tasks.count()
    if stale_count > 0:
        stale_names = list(stale_tasks.values_list("name", flat=True))
        stale_tasks.delete()
        changed_count += stale_count
        logger.info(
            "Removed %d stale periodic task(s): %s",
            stale_count,
            stale_names,
        )

    if changed_count > 0:
        PeriodicTasks.update_changed()
        logger.info(
            "Successfully synchronized %d periodic task(s) (%d changed).",
            len(active_task_names),
            changed_count,
        )
    else:
        logger.info("All periodic tasks are up-to-date.")
