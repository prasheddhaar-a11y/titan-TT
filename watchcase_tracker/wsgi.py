"""
WSGI config for watchcase_tracker project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application
from watchcase_tracker.performance_logging.startup import (
    duration_ms,
    emit_startup_server_once,
    emit_wsgi_event,
    perf_counter,
)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'watchcase_tracker.settings')

emit_wsgi_event('module_loaded')
emit_startup_server_once()
_wsgi_started = perf_counter()
try:
    application = get_wsgi_application()
except Exception:
    emit_wsgi_event('application_error', duration=duration_ms(_wsgi_started))
    raise
emit_wsgi_event('application_created', duration=duration_ms(_wsgi_started))
