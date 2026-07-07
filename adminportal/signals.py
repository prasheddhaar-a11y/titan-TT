import logging

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.sessions.models import Session
from django.dispatch import receiver

from .models import UserActiveSession

logger = logging.getLogger(__name__)


def _get_client_ip(request):
    """Best-effort client IP, honoring a reverse proxy's X-Forwarded-For."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _get_login_source(request):
    """Best-effort classification of where the login originated."""
    path = request.path or ''
    if path.startswith('/admin/'):
        return 'django-admin'
    return 'web'


@receiver(user_logged_in)
def enforce_single_session_on_login(sender, request, user, **kwargs):
    """
    Single-session-per-account enforcement.

    On every successful login, if a different session is already recorded
    as active for this user, that old Django session row is deleted
    server-side (so that browser/device gets logged out on its next
    request), then UserActiveSession is updated to point at the new
    session.
    """
    if request is None:
        return

    session = getattr(request, 'session', None)
    new_session_key = getattr(session, 'session_key', None) if session else None
    if not new_session_key:
        return

    try:
        active_session = UserActiveSession.objects.filter(user=user).first()
        old_session_key = active_session.session_key if active_session else None

        if old_session_key and old_session_key != new_session_key:
            Session.objects.filter(pk=old_session_key).delete()

        UserActiveSession.objects.update_or_create(
            user=user,
            defaults={
                'session_key': new_session_key,
                'ip_address': _get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'login_source': _get_login_source(request),
            },
        )
    except Exception:
        # Session bookkeeping must never block a successful login.
        logger.exception(
            "Failed to enforce single-session-per-account for user_id=%s",
            getattr(user, 'pk', None),
        )


@receiver(user_logged_out)
def clear_active_session_on_logout(sender, request, user, **kwargs):
    """
    On logout, only clear UserActiveSession if it still matches the session
    that is logging out. This stops a stale/old browser tab's logout from
    wiping out a newer active session created by a more recent login
    elsewhere.
    """
    if request is None or user is None:
        return

    session = getattr(request, 'session', None)
    current_session_key = getattr(session, 'session_key', None) if session else None
    if not current_session_key:
        return

    try:
        UserActiveSession.objects.filter(
            user=user, session_key=current_session_key
        ).delete()
    except Exception:
        logger.exception(
            "Failed to clear active session on logout for user_id=%s",
            getattr(user, 'pk', None),
        )