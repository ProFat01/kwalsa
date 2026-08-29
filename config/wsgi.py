"""
WSGI config for SAMS. This is what PythonAnywhere's WSGI configuration
file should import: `from config.wsgi import application`.
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_wsgi_application()
