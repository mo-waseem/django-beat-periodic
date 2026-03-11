from django.core.management.base import BaseCommand

from django_beat_periodic.management.utils import format_schedule, resolve_task_name
from django_beat_periodic.registry import PERIODIC_TASKS
from django_beat_periodic.sync import MANAGED_DESCRIPTION


class Command(BaseCommand):
    help = (
        "List all periodic tasks registered via @periodic_task "
        "and their live database state."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-db",
            action="store_true",
            help="Skip the database lookup and show registry entries only.",
        )

    def handle(self, *args, **options):
        if not PERIODIC_TASKS:
            self.stdout.write(
                self.style.WARNING("No tasks registered via @periodic_task.")
            )
            return

        db_tasks = self._load_db_tasks() if not options["no_db"] else {}

        self.stdout.write("")
        for entry in PERIODIC_TASKS:
            self._print_entry(entry, db_tasks)

        self.stdout.write(
            f"Total: {len(PERIODIC_TASKS)} registered task(s), "
            f"{len(db_tasks)} synced to database.\n"
        )

    def _load_db_tasks(self) -> dict:
        try:
            from django_celery_beat.models import PeriodicTask

            return {
                t.name: t
                for t in PeriodicTask.objects.filter(
                    description=MANAGED_DESCRIPTION
                ).select_related("interval", "crontab")
            }
        except Exception:
            self.stderr.write(
                self.style.WARNING(
                    "Could not query the database (tables may not exist yet). "
                    "Showing registry only.\n"
                )
            )
            return {}

    def _print_entry(self, entry: dict, db_tasks: dict) -> None:
        name = resolve_task_name(entry)
        db_task = db_tasks.get(name)

        enabled_label = (
            self.style.SUCCESS("enabled")
            if entry["enabled"]
            else self.style.ERROR("disabled")
        )
        sync_label = (
            self.style.SUCCESS("✔ synced")
            if db_task
            else self.style.WARNING("✘ not synced")
        )
        last_run = (
            f"  last run: {db_task.last_run_at.strftime('%Y-%m-%d %H:%M:%S %Z')}"
            if db_task and db_task.last_run_at
            else ""
        )

        self.stdout.write(f"  {self.style.HTTP_INFO(name)}")
        self.stdout.write(f"    schedule : {format_schedule(entry)}")
        self.stdout.write(f"    status   : {enabled_label}  {sync_label}{last_run}")
        self.stdout.write("")
