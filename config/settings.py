"""Django settings for the Mars Robot Simulator.

Single-file settings on purpose: this app has no database of its own, no user
accounts and one deployment target (a reviewer's laptop). Anything that would
differ between machines is read from the environment with a working default.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Dev-only fallback. A real deployment must set DJANGO_SECRET_KEY.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "django.contrib.sessions",
    "simulator",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# No models, so no database. Sessions live in signed cookies instead of a
# table, which keeps `runserver` a zero-setup command (no migrate step).
DATABASES = {}
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS: list = []

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- simulation settings -----------------------------------------------------
# The brief's 5x5 is a default, not a constant. Changing these changes the
# board, the bounds checks and the rendered grid together.
SIMULATION_TABLE_WIDTH = int(os.environ.get("SIMULATION_TABLE_WIDTH", 5))
SIMULATION_TABLE_HEIGHT = int(os.environ.get("SIMULATION_TABLE_HEIGHT", 5))
SIMULATION_MAX_LOG_ENTRIES = 80
# Folder of .txt command scripts the UI offers as auto-run input files.
SIMULATION_INPUT_DIR = Path(os.environ.get("SIMULATION_INPUT_DIR", BASE_DIR / "testdata"))
# Pause between commands when an input file plays back in the browser.
SIMULATION_STEP_DELAY_MS = int(os.environ.get("SIMULATION_STEP_DELAY_MS", 650))
