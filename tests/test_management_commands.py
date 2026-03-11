"""Tests for the list_periodic_tasks management command."""

from datetime import datetime
from datetime import timezone as dt_timezone
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

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
        from django_celery_beat.models import PeriodicTask

        from django_beat_periodic.sync import MANAGED_DESCRIPTION, sync_periodic_tasks

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


# ------------------------------------------------------------------ #
# sync_periodic_tasks
# ------------------------------------------------------------------ #


@pytest.mark.django_db
class TestSyncPeriodicTasksCommand:
    @pytest.fixture(autouse=True)
    def _setup(self, populated_registry):
        pass

    def _run(self, *args) -> str:
        out = StringIO()
        call_command("sync_periodic_tasks", *args, stdout=out)
        return out.getvalue()

    # ── real sync ─────────────────────────────────────────────────────

    def test_sync_creates_db_rows(self):
        from django_celery_beat.models import PeriodicTask

        self._run()
        assert PeriodicTask.objects.count() == 3

    def test_sync_prints_success_message(self):
        assert "synced successfully" in self._run()

    def test_sync_is_idempotent(self, reset_sync_guard):
        from django_celery_beat.models import PeriodicTask

        self._run()
        reset_sync_guard
        self._run()
        assert PeriodicTask.objects.count() == 3

    # ── dry-run: no DB writes ──────────────────────────────────────────

    def test_dry_run_writes_nothing_to_db(self):
        from django_celery_beat.models import PeriodicTask

        self._run("--dry-run")
        assert PeriodicTask.objects.count() == 0

    def test_dry_run_shows_create_for_every_new_task(self):
        # all 3 tasks are in code but not in DB yet
        assert self._run("--dry-run").count("[CREATE]") == 3

    def test_dry_run_shows_delete_for_stale_managed_task(self):
        from django_celery_beat.models import IntervalSchedule, PeriodicTask

        from django_beat_periodic.sync import MANAGED_DESCRIPTION

        # insert a managed task that no longer exists in the registry
        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=60, period=IntervalSchedule.SECONDS
        )
        PeriodicTask.objects.create(
            name="stale.task.ghost",
            task="stale.task.ghost",
            interval=schedule,
            description=MANAGED_DESCRIPTION,
        )

        output = self._run("--dry-run")
        assert "[DELETE]" in output
        assert "stale.task.ghost" in output

    def test_dry_run_ignores_manually_created_tasks(self):
        from django_celery_beat.models import IntervalSchedule, PeriodicTask

        # no MANAGED_DESCRIPTION — simulates a task created in the admin
        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=120, period=IntervalSchedule.SECONDS
        )
        PeriodicTask.objects.create(
            name="manual.task.untouched",
            task="manual.task.untouched",
            interval=schedule,
        )

        assert "manual.task.untouched" not in self._run("--dry-run")

    def test_dry_run_shows_noop_for_already_synced_tasks(self, reset_sync_guard):
        from django_beat_periodic.sync import sync_periodic_tasks

        sync_periodic_tasks()
        reset_sync_guard
        assert "[NO-OP]" in self._run("--dry-run")

    def test_dry_run_shows_update_when_field_drifted(self, reset_sync_guard):
        from django_celery_beat.models import PeriodicTask

        from django_beat_periodic.sync import MANAGED_DESCRIPTION, sync_periodic_tasks

        sync_periodic_tasks()

        # simulate someone toggling a task in the admin — next dry-run should catch it
        PeriodicTask.objects.filter(description=MANAGED_DESCRIPTION).update(
            enabled=True
        )

        reset_sync_guard
        output = self._run("--dry-run")
        assert "[UPDATE]" in output
        assert "enabled" in output

    def test_dry_run_prints_summary_line(self):
        assert "Summary" in self._run("--dry-run")


# ------------------------------------------------------------------ #
# enable_periodic_task & disable_periodic_task
# ------------------------------------------------------------------ #


@pytest.mark.django_db
class TestEnablePeriodicTaskCommand:
    @pytest.fixture()
    def disabled_task(self):
        from django_celery_beat.models import IntervalSchedule, PeriodicTask

        from django_beat_periodic.sync import MANAGED_DESCRIPTION

        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=60, period=IntervalSchedule.SECONDS
        )
        return PeriodicTask.objects.create(
            name="myapp.tasks.heartbeat",
            task="myapp.tasks.heartbeat",
            interval=schedule,
            description=MANAGED_DESCRIPTION,
            enabled=False,
        )

    def test_enables_a_disabled_task(self, disabled_task):
        call_command("enable_periodic_task", disabled_task.name, stdout=StringIO())
        disabled_task.refresh_from_db()
        assert disabled_task.enabled is True

    def test_prints_success_message(self, disabled_task):
        out = StringIO()
        call_command("enable_periodic_task", disabled_task.name, stdout=out)
        assert "has been enabled" in out.getvalue()

    def test_already_enabled_prints_warning_and_does_not_save(self, disabled_task):
        # flip it to True first
        disabled_task.enabled = True
        disabled_task.save()

        out = StringIO()
        call_command("enable_periodic_task", disabled_task.name, stdout=out)
        assert "already enabled" in out.getvalue()

    def test_raises_command_error_for_unknown_task(self):
        with pytest.raises(CommandError, match="not found"):
            call_command("enable_periodic_task", "does.not.exist", stdout=StringIO())


@pytest.mark.django_db
class TestDisablePeriodicTaskCommand:
    @pytest.fixture()
    def enabled_task(self):
        from django_celery_beat.models import IntervalSchedule, PeriodicTask

        from django_beat_periodic.sync import MANAGED_DESCRIPTION

        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=60, period=IntervalSchedule.SECONDS
        )
        return PeriodicTask.objects.create(
            name="myapp.tasks.heartbeat",
            task="myapp.tasks.heartbeat",
            interval=schedule,
            description=MANAGED_DESCRIPTION,
            enabled=True,
        )

    def test_disables_an_enabled_task(self, enabled_task):
        call_command("disable_periodic_task", enabled_task.name, stdout=StringIO())
        enabled_task.refresh_from_db()
        assert enabled_task.enabled is False

    def test_prints_success_message(self, enabled_task):
        out = StringIO()
        call_command("disable_periodic_task", enabled_task.name, stdout=out)
        assert "has been disabled" in out.getvalue()

    def test_already_disabled_prints_warning_and_does_not_save(self, enabled_task):
        # flip it to False first
        enabled_task.enabled = False
        enabled_task.save()

        out = StringIO()
        call_command("disable_periodic_task", enabled_task.name, stdout=out)
        assert "already disabled" in out.getvalue()

    def test_raises_command_error_for_unknown_task(self):
        with pytest.raises(CommandError, match="not found"):
            call_command("disable_periodic_task", "does.not.exist", stdout=StringIO())

    def test_full_roundtrip(self, enabled_task):
        # disable
        call_command("disable_periodic_task", enabled_task.name, stdout=StringIO())
        enabled_task.refresh_from_db()
        assert enabled_task.enabled is False

        # enable again
        call_command("enable_periodic_task", enabled_task.name, stdout=StringIO())
        enabled_task.refresh_from_db()
        assert enabled_task.enabled is True
