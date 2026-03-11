"""Tests for the list_periodic_tasks management command."""

from io import StringIO
from datetime import timezone as dt_timezone
from datetime import datetime

import pytest
from django.core.management import call_command


# ------------------------------------------------------------------ #
# list_periodic_tasks — populated registry
# ------------------------------------------------------------------ #


@pytest.mark.django_db
class TestListPeriodicTasksCommand:
    @pytest.fixture(autouse=True)
    def _setup(self, populated_registry):
        pass

    def _run(self, *args) -> str:
        out = StringIO()
        call_command("list_periodic_tasks", *args, stdout=out)
        return out.getvalue()

    def test_shows_all_registered_task_names(self):
        output = self._run()
        assert "heartbeat" in output
        assert "morning_report" in output

    def test_shows_custom_name_instead_of_func_path(self):
        # name= kwarg on the decorator should win over the auto-generated path
        assert "custom-disabled-task" in self._run()

    def test_shows_interval_schedule(self):
        assert "every 1m" in self._run()

    def test_shows_crontab_schedule(self):
        assert "0 9 * * 1-5" in self._run()

    def test_shows_not_synced_when_db_is_empty(self):
        # nothing has been synced yet — all tasks should be marked as not synced
        assert "not synced" in self._run()

    def test_shows_synced_after_sync(self):
        from django_beat_periodic.sync import sync_periodic_tasks

        sync_periodic_tasks()
        assert "synced" in self._run()

    def test_shows_last_run_at_when_task_has_run(self):
        from django_beat_periodic.sync import sync_periodic_tasks, MANAGED_DESCRIPTION
        from django_celery_beat.models import PeriodicTask

        sync_periodic_tasks()

        # Simulate a task that has already been picked up by the beat scheduler
        last_run = datetime(2025, 1, 15, 9, 30, 0, tzinfo=dt_timezone.utc)
        PeriodicTask.objects.filter(description=MANAGED_DESCRIPTION).update(
            last_run_at=last_run
        )

        assert "last run: 2025-01-15" in self._run()

    def test_total_count_line(self):
        assert "3 registered task(s)" in self._run()

    def test_no_db_flag_skips_database(self):
        # --no-db should still show registry tasks without hitting the DB
        assert "heartbeat" in self._run("--no-db")


# ------------------------------------------------------------------ #
# list_periodic_tasks — empty registry
# ------------------------------------------------------------------ #


@pytest.mark.django_db
class TestListPeriodicTasksEmptyRegistry:
    @pytest.fixture(autouse=True)
    def _setup(self, clean_registry, reset_sync_guard):
        pass

    def test_empty_registry_prints_warning(self):
        out = StringIO()
        call_command("list_periodic_tasks", stdout=out)
        assert "No tasks registered" in out.getvalue()
