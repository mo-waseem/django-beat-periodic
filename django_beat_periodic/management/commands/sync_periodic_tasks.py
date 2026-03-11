"""Management command: sync @periodic_task decorators to the database.

Pass ``--dry-run`` to preview what would change without writing anything.
"""

from django.core.management.base import BaseCommand

from django_beat_periodic.management.utils import resolve_task_name
from django_beat_periodic.registry import PERIODIC_TASKS
from django_beat_periodic.sync import MANAGED_DESCRIPTION


class Command(BaseCommand):
    help = (
        "Sync @periodic_task decorators to the database. "
        "Use --dry-run to preview changes without writing."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview creates / updates / deletes without touching the database.",
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            self._dry_run()
        else:
            self._sync()

    def _sync(self) -> None:
        import django_beat_periodic.sync as sync_mod
        from django_beat_periodic.sync import sync_periodic_tasks

        # Reset the guard so the command always runs a fresh sync, even
        # if AppConfig.ready() has already fired (common in dev with auto-reload).
        sync_mod._already_synced = False
        sync_periodic_tasks()
        self.stdout.write(self.style.SUCCESS("Periodic tasks synced successfully."))

    def _dry_run(self) -> None:
        self.stdout.write(
            self.style.WARNING("\nDRY RUN — no changes will be written.\n")
        )

        try:
            from django_celery_beat.models import PeriodicTask
        except Exception:
            self.stderr.write(
                self.style.ERROR(
                    "Cannot import django_celery_beat models. Have you run migrations?"
                )
            )
            return

        code_tasks = {resolve_task_name(e): e for e in PERIODIC_TASKS}
        db_tasks = {
            t.name: t
            for t in PeriodicTask.objects.filter(description=MANAGED_DESCRIPTION)
        }

        to_create = sorted(set(code_tasks) - set(db_tasks))
        to_delete = sorted(set(db_tasks) - set(code_tasks))
        to_inspect = sorted(set(code_tasks) & set(db_tasks))

        for name in to_create:
            self.stdout.write(f"  {self.style.SUCCESS('[CREATE]')}  {name}")

        for name in to_delete:
            self.stdout.write(f"  {self.style.ERROR('[DELETE]')}  {name}")

        updated_count = 0
        for name in to_inspect:
            changed = self._detect_drift(code_tasks[name], db_tasks[name])
            if changed:
                updated_count += 1
                self.stdout.write(
                    f"  {self.style.WARNING('[UPDATE]')}  {name}"
                    f"  (fields: {', '.join(changed)})"
                )
            else:
                self.stdout.write(f"  {self.style.HTTP_INFO('[NO-OP]')}   {name}")

        self.stdout.write(
            f"\nSummary: "
            f"{self.style.SUCCESS(str(len(to_create)) + ' to create')}  "
            f"{self.style.WARNING(str(updated_count) + ' to update')}  "
            f"{self.style.ERROR(str(len(to_delete)) + ' to delete')}\n"
        )

    @staticmethod
    def _detect_drift(entry: dict, db_task) -> list[str]:
        """Return field names whose live DB value differs from the registry entry."""
        import json

        kwargs = entry["kwargs"].copy()
        kwargs.pop("name", None)

        candidates = {
            "enabled": entry["enabled"],
            "queue": kwargs.pop("queue", None),
            "priority": kwargs.pop("priority", None),
            "args": json.dumps(kwargs.pop("args", [])),
            "kwargs": json.dumps(kwargs.pop("kwargs", {})),
        }

        changed = [
            field
            for field, value in candidates.items()
            if getattr(db_task, field, None) != value
        ]

        if entry["interval"] is not None and db_task.interval_id is None:
            changed.append("interval")
        if entry["crontab"] is not None and db_task.crontab_id is None:
            changed.append("crontab")

        return changed
