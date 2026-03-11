from __future__ import annotations

from datetime import timedelta


def resolve_task_name(entry: dict) -> str:
    func = entry["func"]
    task_path = f"{func.__module__}.{func.__name__}"
    return entry["kwargs"].get("name", task_path)


def format_schedule(entry: dict) -> str:
    interval = entry["interval"]
    crontab = entry["crontab"]

    if interval is not None:
        total = int(
            interval.total_seconds() if isinstance(interval, timedelta) else interval
        )
        if total < 60:
            return f"every {total}s"
        if total < 3600:
            return f"every {total // 60}m"
        return f"every {total // 3600}h"

    if isinstance(crontab, str):
        return f"cron({crontab})"

    if isinstance(crontab, dict):
        expression = " ".join(
            [
                crontab.get("minute", "*"),
                crontab.get("hour", "*"),
                crontab.get("day_of_month", "*"),
                crontab.get("month_of_year", "*"),
                crontab.get("day_of_week", "*"),
            ]
        )
        return f"cron({expression})"

    return "no schedule"
