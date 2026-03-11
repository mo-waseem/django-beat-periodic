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
