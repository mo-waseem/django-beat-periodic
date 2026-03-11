"""Management command: disable a periodic task by name."""

from django_beat_periodic.management.commands._base_toggle import BaseToggleCommand


class Command(BaseToggleCommand):
    help = "Disable a PeriodicTask by its exact name."
    target_enabled = False
