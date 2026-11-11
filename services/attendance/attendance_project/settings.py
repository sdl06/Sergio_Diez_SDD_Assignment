import os
from pathlib import Path
from secrets import token_urlsafe

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or token_urlsafe(48)
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() in {"true", "1", "yes"}
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

INSTALLED_APPS = ["bus_tracker_app"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware"]

ROOT_URLCONF = "attendance_project.urls"
WSGI_APPLICATION = "attendance_project.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    },
}
TIME_ZONE = "UTC"
USE_TZ = True
