"""Tests for the @periodic_task decorator and sync_periodic_tasks()."""

from datetime import timedelta

import pytest

from django_beat_periodic.registry import PERIODIC_TASKS


# ------------------------------------------------------------------ #
# Helpers — define some dummy tasks via the decorator
# ------------------------------------------------------------------ #


def _make_tasks():
    """Import the decorator and create sample tasks.

    We do this lazily so the Celery app is already set up (via conftest).
    """
    from django_beat_periodic.decorators import periodic_task

    @periodic_task(interval=30)
    def every_30_seconds():
        return "tick"

    @periodic_task(interval=timedelta(minutes=5))
    def every_five_minutes():
        return "tock"

    @periodic_task(crontab="0 */2 * * *")
    def every_two_hours_cron():
        return "cron"

    @periodic_task(
        crontab={"minute": "0", "hour": "3", "day_of_week": "monday"},
    )
    def monday_3am():
        return "monday"

    @periodic_task(interval=10, enabled=False, name="custom-task-name", queue="low")
    def disabled_with_extras():
        return "off"

    return {
        "every_30_seconds": every_30_seconds,
        "every_five_minutes": every_five_minutes,
        "every_two_hours_cron": every_two_hours_cron,
        "monday_3am": monday_3am,
        "disabled_with_extras": disabled_with_extras,
    }


# ------------------------------------------------------------------ #
# Registry tests
# ------------------------------------------------------------------ #


class TestPeriodicTaskDecorator:
    """Verify that the decorator populates the PERIODIC_TASKS registry."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Clear the registry before each test, then register tasks."""
        PERIODIC_TASKS.clear()
        self.tasks = _make_tasks()

    def test_registry_length(self):
        assert len(PERIODIC_TASKS) == 5

    def test_interval_int_is_stored(self):
        entry = PERIODIC_TASKS[0]
        assert entry["interval"] == 30
        assert entry["crontab"] is None
        assert entry["enabled"] is True

    def test_interval_timedelta_is_stored(self):
        entry = PERIODIC_TASKS[1]
        assert entry["interval"] == timedelta(minutes=5)

    def test_crontab_str_is_stored(self):
        entry = PERIODIC_TASKS[2]
        assert entry["crontab"] == "0 */2 * * *"
        assert entry["interval"] is None

    def test_crontab_dict_is_stored(self):
        entry = PERIODIC_TASKS[3]
        assert entry["crontab"] == {
            "minute": "0",
            "hour": "3",
            "day_of_week": "monday",
        }

    def test_disabled_and_extra_kwargs(self):
        entry = PERIODIC_TASKS[4]
        assert entry["enabled"] is False
        assert entry["kwargs"]["name"] == "custom-task-name"
        assert entry["kwargs"]["queue"] == "low"


# ------------------------------------------------------------------ #
# Sync tests (requires database)
# ------------------------------------------------------------------ #


@pytest.mark.django_db
class TestSyncPeriodicTasks:
    """Verify that sync_periodic_tasks() creates the expected DB rows."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Reset the registry and sync flag before each test."""
        import django_beat_periodic.sync as sync_mod

        PERIODIC_TASKS.clear()
        sync_mod._already_synced = False
        self.tasks = _make_tasks()

    def test_creates_periodic_task_rows(self):
        from django_celery_beat.models import PeriodicTask

        from django_beat_periodic.sync import sync_periodic_tasks

        sync_periodic_tasks()

        assert PeriodicTask.objects.count() == 5

    def test_interval_schedule_created(self):
        from django_celery_beat.models import IntervalSchedule

        from django_beat_periodic.sync import sync_periodic_tasks

        sync_periodic_tasks()

        # 30s, 300s (5 min), 10s → 3 distinct intervals
        assert IntervalSchedule.objects.count() == 3

    def test_crontab_schedule_created(self):
        from django_celery_beat.models import CrontabSchedule

        from django_beat_periodic.sync import sync_periodic_tasks

        sync_periodic_tasks()

        # "0 */2 * * *" and the dict-based monday 3am → 2 crontabs
        assert CrontabSchedule.objects.count() == 2

    def test_custom_name_and_queue(self):
        from django_celery_beat.models import PeriodicTask

        from django_beat_periodic.sync import sync_periodic_tasks

        sync_periodic_tasks()

        pt = PeriodicTask.objects.get(name="custom-task-name")
        assert pt.enabled is False
        assert pt.queue == "low"

    def test_idempotent_sync(self):
        """Running sync twice should not create duplicate rows."""
        import django_beat_periodic.sync as sync_mod

        from django_celery_beat.models import PeriodicTask

        from django_beat_periodic.sync import sync_periodic_tasks

        sync_periodic_tasks()
        count_after_first = PeriodicTask.objects.count()

        # Reset the guard so sync runs again
        sync_mod._already_synced = False
        sync_periodic_tasks()
        count_after_second = PeriodicTask.objects.count()

        assert count_after_first == count_after_second == 5

    def test_update_detects_changes(self):
        """If the decorator changes interval, sync should update the row."""
        import django_beat_periodic.sync as sync_mod

        from django_celery_beat.models import PeriodicTask

        from django_beat_periodic.sync import sync_periodic_tasks

        sync_periodic_tasks()

        # Manually flip enabled to True for the disabled task
        pt = PeriodicTask.objects.get(name="custom-task-name")
        pt.enabled = True
        pt.save()

        # Re-sync should flip it back to False (the decorator says enabled=False)
        sync_mod._already_synced = False
        sync_periodic_tasks()

        pt.refresh_from_db()
        assert pt.enabled is False
