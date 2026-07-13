"""
ASGI config for watchcase_tracker project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application
from watchcase_tracker.performance_logging.startup import (
    duration_ms,
    emit_asgi_event,
    emit_startup_server_once,
    perf_counter,
)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'watchcase_tracker.settings')

emit_asgi_event('module_loaded')
emit_startup_server_once()
_asgi_started = perf_counter()
try:
    application = get_asgi_application()
except Exception:
    emit_asgi_event('application_error', duration=duration_ms(_asgi_started))
    raise
emit_asgi_event('application_created', duration=duration_ms(_asgi_started))
