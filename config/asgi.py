"""
ASGI config for SAMS. Not used by PythonAnywhere's classic WSGI hosting,
but kept so the project can move to an async-capable host later without
restructuring (Django 6.0 leans further into async views/tasks).
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_asgi_application()
