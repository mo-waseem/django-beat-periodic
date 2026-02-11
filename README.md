# django-beat-periodic 🥁

[![PyPI version](https://img.shields.io/pypi/v/django-beat-periodic.svg)](https://pypi.org/project/django-beat-periodic/)
[![PyPI downloads](https://img.shields.io/pypi/dm/django-beat-periodic.svg)](https://pypi.org/project/django-beat-periodic/)

Auto-populate [django-celery-beat](https://github.com/celery/django-celery-beat) `PeriodicTask` objects with a simple decorator — no manual admin setup required.

## Installation 📥

```bash
pip install django-beat-periodic
```

## Why Use This? 🤔

### 1. Periodic Tasks as Code — No Admin Required

Define schedules directly in your codebase. No need to manually create or update periodic tasks through the Django admin — everything is synced automatically on startup.

### 2. Dynamic, Environment-Aware Scheduling

Use environment variables or Django settings to change task intervals per environment — without touching the database:

```python
import os
from django_beat_periodic import periodic_task

CLEANUP_INTERVAL = int(os.getenv("CLEANUP_INTERVAL", "3600"))  # 1h default

@periodic_task(interval=CLEANUP_INTERVAL)
def cleanup_old_records():
    ...
```

Run every 10 seconds in dev, every hour in production — same code, different env vars.

### 3. Version-Controlled Schedules

Since schedules live in code, every change is tracked in Git — you get full history, code review, and easy rollbacks. No more wondering who changed a task's interval in the admin.

### 4. Consistent Across Team & Deployments

New team members or fresh deployments get the correct periodic tasks automatically — no manual setup, no "did you remember to add the periodic task?" checklist.

### 5. Single Source of Truth

The decorator is the authoritative definition. If someone changes a task's settings in the admin, the next deployment will reset it to match the code — preventing configuration drift.

### 6. Automatic Cleanup of Stale Tasks

When you remove a `@periodic_task` decorator from your code, `django-beat-periodic` automatically deletes the corresponding `PeriodicTask` row from the database on the next startup. This keeps your database clean and ensures no ghost tasks are running.

> [!NOTE]
> It only deletes tasks that were originally created by the package (marked with a specific description). Manually created tasks in the Django admin are never touched.

## Quick Start 🚀

### 1. Add to `INSTALLED_APPS`

```python
INSTALLED_APPS = [
    # ...
    "django_celery_beat",
    "django_beat_periodic",   # must come AFTER django_celery_beat
    # ...
]
```

### 2. Decorate Your Tasks

```python
# myapp/tasks.py
from django_beat_periodic import periodic_task

@periodic_task(interval=60)
def heartbeat():
    """Runs every 60 seconds."""
    print("alive!")

@periodic_task(crontab="*/5 * * * *")
def generate_report():
    """Runs every 5 minutes (cron-style)."""
    build_report()

@periodic_task(interval=300, enabled=False)
def expensive_cleanup():
    """Registered but disabled by default."""
    cleanup_old_records()
```

### 3. Done! ✨

On Django startup, `django_beat_periodic` will automatically create or update the
corresponding `PeriodicTask`, `IntervalSchedule`, and `CrontabSchedule` rows in your
database. The Celery Beat scheduler picks them up immediately.

## Decorator Options ⚙️

| Parameter  | Type                    | Description                                       |
| ---------- | ----------------------- | ------------------------------------------------- |
| `interval` | `int` or `timedelta`    | Run every N seconds (or a timedelta)              |
| `crontab`  | `str` or `dict`         | Cron expression (`"* * * * *"`) or dict of fields |
| `enabled`  | `bool` (default `True`) | Whether the task is enabled                       |
| `name`     | `str`                   | Custom task name (defaults to module path)        |
| `queue`    | `str`                   | Celery queue to route to                          |
| `priority` | `int`                   | Task priority                                     |
| `args`     | `list`                  | Positional arguments for the task                 |
| `kwargs`   | `dict`                  | Keyword arguments for the task                    |

## How It Works 🛠️

1. `@periodic_task` registers metadata (schedule, enabled, etc.) in an internal registry and wraps the function with Celery's `@app.task`.
2. When Django starts, `DjangoBeatPeriodicConfig.ready()` calls `sync_periodic_tasks()`.
3. `sync_periodic_tasks()` iterates the registry and creates or updates `django_celery_beat` database objects, only writing when something actually changed.

## Requirements 📋

- Python ≥ 3.9
- Django ≥ 3.2
- Celery ≥ 5.0
- django-celery-beat ≥ 2.0

## Contributing 🤝

Contributions are welcome! To set up the project locally:

1. Clone the repository:
   ```bash
   git clone https://github.com/mo-waseem/django-beat-periodic.git
   cd django-beat-periodic
   ```

2. Install dependencies (using `uv` or `pip`):
   ```bash
   uv venv
   source .venv/bin/activate
   uv pip install -e ".[test]"
   ```

3. Run tests to ensure everything is working:
   ```bash
   pytest
   ```

Feel free to open an issue or submit a pull request!

## License 📄

MIT

---

**PyPI:** [https://pypi.org/project/django-beat-periodic/](https://pypi.org/project/django-beat-periodic/)
