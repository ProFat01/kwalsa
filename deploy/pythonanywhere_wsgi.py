# SAMS — PythonAnywhere WSGI configuration file
#
# HOW TO USE:
# 1. In the PythonAnywhere Web tab, set the WSGI configuration file to
#    point at this file: /home/yourusername/sams/deploy/pythonanywhere_wsgi.py
# 2. Replace PYTHONANYWHERE_USERNAME below with your actual PythonAnywhere username.
# 3. Set all required environment variables in the PythonAnywhere Web tab
#    (see "Step 2: PythonAnywhere Web tab configuration" in
#    PRODUCTION_DEPLOYMENT.md for the complete variable list).
# 4. Reload the web app from the PythonAnywhere Web tab.

import os
import sys

# ── replace with your real username ──────────────────────────────────────────
PYTHONANYWHERE_USERNAME = "yourusername"
# ─────────────────────────────────────────────────────────────────────────────

project_root = f"/home/{PYTHONANYWHERE_USERNAME}/sams"
venv_site_packages = f"/home/{PYTHONANYWHERE_USERNAME}/.virtualenvs/sams/lib/python3.12/site-packages"

if project_root not in sys.path:
    sys.path.insert(0, project_root)
if venv_site_packages not in sys.path:
    sys.path.insert(1, venv_site_packages)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

from django.core.wsgi import get_wsgi_application  # noqa: E402
application = get_wsgi_application()
