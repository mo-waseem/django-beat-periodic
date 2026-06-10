from django.core.management.base import BaseCommand, CommandError

from django_beat_periodic.sync import MANAGED_DESCRIPTION


class Command(BaseCommand):
    help = (
        "List live django-celery-beat PeriodicTask rows managed by "
        "django-beat-periodic. Use --all to include unmanaged rows."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Include unmanaged django-celery-beat PeriodicTask rows.",
        )

    def handle(self, *args, **options):
        tasks = self._load_db_tasks(include_all=options["all"])
        if not tasks:
            message = (
                "No periodic tasks found."
                if options["all"]
                else "No managed periodic tasks found. Run sync_periodic_tasks first."
            )
            self.stdout.write(self.style.WARNING(message))
            return

        self.stdout.write("")

        for task in tasks:
            self._print_task(task, include_management_label=options["all"])

        self.stdout.write(
            f"Total: {len(tasks)} "
            f"{'periodic task(s)' if options['all'] else 'managed task(s)'} found.\n"
        )

    def _load_db_tasks(self, *, include_all: bool) -> list:
        try:
            from django_celery_beat.models import PeriodicTask
        except Exception as exc:
            raise CommandError(
                "Cannot import django_celery_beat models. Is django-celery-beat "
                "installed and included in INSTALLED_APPS?"
            ) from exc

        query = PeriodicTask.objects.all()
        if not include_all:
            query = query.filter(description=MANAGED_DESCRIPTION)

        try:
            return list(
                query.select_related(
                    "interval", "crontab", "solar", "clocked"
                ).order_by("name")
            )
        except Exception as exc:
            raise CommandError(
                "Could not query django_celery_beat PeriodicTask rows. "
                "Have you run migrations?"
            ) from exc

    def _print_task(self, task, *, include_management_label: bool) -> None:
        enabled_label = (
            self.style.SUCCESS("enabled")
            if task.enabled
            else self.style.ERROR("disabled")
        )
        managed_label = (
            self.style.SUCCESS("managed")
            if task.description == MANAGED_DESCRIPTION
            else self.style.WARNING("unmanaged")
        )
        last_run = (
            f"  last run: {task.last_run_at.strftime('%Y-%m-%d %H:%M:%S %Z')}"
            if task.last_run_at
            else ""
        )

        status_parts = [enabled_label]
        if include_management_label:
            status_parts.append(managed_label)

        self.stdout.write(f"  {self.style.HTTP_INFO(task.name)}")
        self.stdout.write(f"    task     : {task.task}")
        self.stdout.write(f"    schedule : {self._format_db_schedule(task)}")
        self.stdout.write(f"    status   : {'  '.join(status_parts)}{last_run}")
        self.stdout.write("")

    @staticmethod
    def _format_db_schedule(task) -> str:
        if task.interval_id:
            return f"every {task.interval.every} {task.interval.period}"

        if task.crontab_id:
            return "cron({} {} {} {} {})".format(
                task.crontab.minute,
                task.crontab.hour,
                task.crontab.day_of_month,
                task.crontab.month_of_year,
                task.crontab.day_of_week,
            )

        if getattr(task, "solar_id", None):
            return "solar({} at {}, {})".format(
                task.solar.event,
                task.solar.latitude,
                task.solar.longitude,
            )

        if getattr(task, "clocked_id", None):
            return f"clocked({task.clocked.clocked_time})"

        return "no schedule"
