#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path

import environ


def main():
    """Run administrative tasks."""
    # Load environment variables from .env before selecting
    # the Django settings module.
    BASE_DIR = Path(__file__).resolve().parent
    env = environ.Env()
    environ.Env.read_env(BASE_DIR / ".env")

    # Use the settings module specified in .env.
    # Fall back to development settings if none is specified.
    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        env("DJANGO_SETTINGS_MODULE", default="config.settings.development"),
    )

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()