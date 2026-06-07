"""Tests for the management commands."""

from datetime import datetime
from datetime import timezone as dt_timezone
from io import StringIO

import pytest
from django.core.management import CommandError, call_command


# ------------------------------------------------------------------ #
# AppConfig startup sync guard
# ------------------------------------------------------------------ #


class TestManagementCommandStartupSyncGuard:
    @pytest.mark.parametrize(
        "command",
        ["disable_periodic_task", "enable_periodic_task", "list_periodic_tasks"],
    )
    def test_skips_startup_sync_for_live_db_commands(self, monkeypatch, command):
        from django_beat_periodic.apps import DjangoBeatPeriodicConfig

        monkeypatch.setattr("sys.argv", ["manage.py", command])

        assert DjangoBeatPeriodicConfig._should_skip_startup_sync() is True

    @pytest.mark.parametrize("command", ["runserver", "sync_periodic_tasks"])
    def test_keeps_startup_sync_for_other_commands(self, monkeypatch, command):
        from django_beat_periodic.apps import DjangoBeatPeriodicConfig

        monkeypatch.setattr("sys.argv", ["manage.py", command])

        assert DjangoBeatPeriodicConfig._should_skip_startup_sync() is False


# ------------------------------------------------------------------ #
# list_periodic_tasks — database-backed output
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

    def _sync(self):
        from django_beat_periodic.sync import sync_periodic_tasks

        sync_periodic_tasks()

    def test_shows_synced_managed_task_names(self):
        self._sync()
        output = self._run()
        assert "heartbeat" in output
        assert "morning_report" in output

    def test_shows_custom_name_instead_of_func_path(self):
        self._sync()
        # name= kwarg on the decorator should win over the auto-generated path
        assert "custom-disabled-task" in self._run()

    def test_shows_interval_schedule(self):
        self._sync()
        assert "every 60 seconds" in self._run()

    def test_shows_crontab_schedule(self):
        self._sync()
        assert "cron(0 9 * * 1-5)" in self._run()

    def test_does_not_show_unsynced_registry_entries(self):
        output = self._run()
        assert "No managed periodic tasks found" in output
        assert "heartbeat" not in output

    def test_shows_live_enabled_state_from_database(self):
        from django_celery_beat.models import PeriodicTask

        from django_beat_periodic.sync import MANAGED_DESCRIPTION

        self._sync()
        PeriodicTask.objects.filter(description=MANAGED_DESCRIPTION).update(
            enabled=False
        )
        assert "disabled" in self._run()

    def test_shows_last_run_at_when_task_has_run(self):
        from django_celery_beat.models import PeriodicTask

        from django_beat_periodic.sync import MANAGED_DESCRIPTION

        self._sync()

        # Simulate a task that has already been picked up by the beat scheduler
        last_run = datetime(2025, 1, 15, 9, 30, 0, tzinfo=dt_timezone.utc)
        PeriodicTask.objects.filter(description=MANAGED_DESCRIPTION).update(
            last_run_at=last_run
        )

        assert "last run: 2025-01-15" in self._run()

    def test_total_count_line(self):
        self._sync()
        assert "3 managed task(s)" in self._run()

    def test_default_output_hides_unmanaged_tasks(self):
        from django_celery_beat.models import IntervalSchedule, PeriodicTask

        self._sync()
        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=120, period=IntervalSchedule.SECONDS
        )
        PeriodicTask.objects.create(
            name="manual.task.untouched",
            task="manual.task.untouched",
            interval=schedule,
        )

        assert "manual.task.untouched" not in self._run()

    def test_all_flag_shows_unmanaged_tasks_with_label(self):
        from django_celery_beat.models import IntervalSchedule, PeriodicTask

        self._sync()
        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=120, period=IntervalSchedule.SECONDS
        )
        PeriodicTask.objects.create(
            name="manual.task.untouched",
            task="manual.task.untouched",
            interval=schedule,
        )

        output = self._run("--all")
        assert "manual.task.untouched" in output
        assert "unmanaged" in output
        assert "enabled  managed" in output

    def test_all_flag_shows_total_periodic_task_count(self):
        self._sync()
        assert "3 periodic task(s)" in self._run("--all")


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
        assert "No managed periodic tasks found" in out.getvalue()


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

    def test_dry_run_shows_update_when_schedule_type_changed(self, reset_sync_guard):
        from django_beat_periodic.sync import sync_periodic_tasks, MANAGED_DESCRIPTION
        from django_celery_beat.models import PeriodicTask, CrontabSchedule

        sync_periodic_tasks()

        # simulate a task that switched from interval to crontab in the DB
        crontab, _ = CrontabSchedule.objects.get_or_create(
            minute="0", hour="9", day_of_week="*", day_of_month="*", month_of_year="*"
        )
        PeriodicTask.objects.filter(description=MANAGED_DESCRIPTION).update(
            interval=None, crontab=crontab
        )

        reset_sync_guard
        output = self._run("--dry-run")
        assert "[UPDATE]" in output


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

    def test_prints_temporary_override_warning(self, disabled_task):
        out = StringIO()
        call_command("enable_periodic_task", disabled_task.name, stdout=out)
        assert "WARNING: This is a temporary database override" in out.getvalue()
        assert "@periodic_task decorator" in out.getvalue()

    def test_already_enabled_prints_warning_and_does_not_save(self, disabled_task):
        # flip it to True first
        disabled_task.enabled = True
        disabled_task.save()

        out = StringIO()
        call_command("enable_periodic_task", disabled_task.name, stdout=out)
        assert "already enabled" in out.getvalue()
        assert "WARNING: This is a temporary database override" in out.getvalue()

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

    def test_prints_temporary_override_warning(self, enabled_task):
        out = StringIO()
        call_command("disable_periodic_task", enabled_task.name, stdout=out)
        assert "WARNING: This is a temporary database override" in out.getvalue()
        assert "@periodic_task decorator" in out.getvalue()

    def test_already_disabled_prints_warning_and_does_not_save(self, enabled_task):
        # flip it to False first
        enabled_task.enabled = False
        enabled_task.save()

        out = StringIO()
        call_command("disable_periodic_task", enabled_task.name, stdout=out)
        assert "already disabled" in out.getvalue()
        assert "WARNING: This is a temporary database override" in out.getvalue()

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
