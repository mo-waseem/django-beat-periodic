"""Management command: enable a periodic task by name."""

from django_beat_periodic.management.commands._base_toggle import BaseToggleCommand


class Command(BaseToggleCommand):
    help = "Enable a PeriodicTask by its exact name."
    target_enabled = True
