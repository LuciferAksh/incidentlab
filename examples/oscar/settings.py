"""Local-only overrides layered on Oscar's own sandbox settings."""

import os
from pathlib import Path

from settings import *  # noqa: F403 - upstream sandbox settings, explicitly on sys.path
from settings import INSTALLED_APPS as OSCAR_APPS

ROOT = Path(__file__).resolve().parents[2]
INSTALLED_APPS = [app for app in OSCAR_APPS if app != "easy_thumbnails"]
SECRET_KEY = os.environ["OSCAR_LOCAL_SECRET"]
DEBUG = False
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(ROOT / "data/oscar-shop.sqlite3"),
        "OPTIONS": {"timeout": 0.25},
        "ATOMIC_REQUESTS": True,
    }
}
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
STATIC_ROOT = str(ROOT / "data/oscar-static")
MEDIA_ROOT = str(ROOT / "data/oscar-media")
ROOT_URLCONF = "examples.oscar.urls"
HAYSTACK_CONNECTIONS = {
    "default": {
        "ENGINE": "haystack.backends.whoosh_backend.WhooshEngine",
        "PATH": str(ROOT / "data/oscar-search"),
    }
}
HAYSTACK_SIGNAL_PROCESSOR = "haystack.signals.BaseSignalProcessor"
