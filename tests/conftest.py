import os

import django
import pytest


def pytest_configure():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
    django.setup()


@pytest.fixture()
def clean_registry():
    from django_beat_periodic.registry import PERIODIC_TASKS

    PERIODIC_TASKS.clear()
    yield PERIODIC_TASKS
    PERIODIC_TASKS.clear()


@pytest.fixture()
def reset_sync_guard():
    import django_beat_periodic.sync as sync_mod

    sync_mod._already_synced = False
    yield
    sync_mod._already_synced = False


@pytest.fixture()
def populated_registry(clean_registry, reset_sync_guard):
    from django_beat_periodic.decorators import periodic_task

    @periodic_task(interval=60)
    def heartbeat():
        return "alive"

    @periodic_task(crontab="0 9 * * 1-5")
    def morning_report():
        return "report"

    @periodic_task(
        interval=300, enabled=False, name="custom-disabled-task", queue="low"
    )
    def expensive_cleanup():
        return "clean"

    return clean_registry


@pytest.fixture()
def extended_registry(clean_registry, reset_sync_guard):
    """Registry covering all schedule variations for utils coverage."""
    from django_beat_periodic.decorators import periodic_task
    from datetime import timedelta

    @periodic_task(interval=30)  # seconds branch
    def task_seconds(): ...

    @periodic_task(interval=timedelta(minutes=5))  # timedelta + minutes branch
    def task_minutes(): ...

    @periodic_task(interval=timedelta(hours=2))  # hours branch
    def task_hours(): ...

    @periodic_task(
        crontab={"minute": "0", "hour": "9", "day_of_week": "monday"}
    )  # dict branch
    def task_crontab_dict(): ...

    return clean_registry
