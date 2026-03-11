"""
Private base class for enable_periodic_task and disable_periodic_task.
"""

from django.core.management.base import BaseCommand, CommandError
from django_celery_beat.models import PeriodicTask, PeriodicTasks


class BaseToggleCommand(BaseCommand):
    """Set ``PeriodicTask.enabled`` to a fixed target value."""

    # Subclasses declare the desired state — no other changes needed.
    target_enabled: bool

    def add_arguments(self, parser):
        parser.add_argument(
            "task_name",
            type=str,
            help="Exact name of the PeriodicTask to toggle.",
        )

    def handle(self, *args, **options):
        task_name: str = options["task_name"]
        target = self.target_enabled
        state_label = "enabled" if target else "disabled"

        try:
            task = PeriodicTask.objects.get(name=task_name)
        except PeriodicTask.DoesNotExist:
            raise CommandError(
                f'PeriodicTask "{task_name}" not found. '
                'Run "manage.py list_periodic_tasks" to see available names.'
            )

        if task.enabled == target:
            self.stdout.write(
                self.style.WARNING(
                    f'Task "{task_name}" is already {state_label}. Nothing to do.'
                )
            )
            return

        task.enabled = target
        task.save(update_fields=["enabled"])
        PeriodicTasks.update_changed()

        self.stdout.write(
            self.style.SUCCESS(f'Task "{task_name}" has been {state_label}.')
        )
