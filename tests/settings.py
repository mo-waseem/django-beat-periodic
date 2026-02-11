"""Minimal Django settings for running the test suite."""

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django_celery_beat",
    "django_beat_periodic",
]

USE_TZ = True

CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

SECRET_KEY = "test-secret-key-not-for-production"
