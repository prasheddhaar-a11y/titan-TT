from django.conf import settings

from adminportal.services import get_user_allowed_module_names, is_admin_user


def user_permissions(request):
    """Add user permission context to all templates.
    """
    # Exposed to base.html so the frontend session guard knows the idle
    # timeout window (used to proactively detect session expiry).
    session_cookie_age = getattr(settings, 'SESSION_COOKIE_AGE', 900)

    if request.user.is_authenticated:
        allowed_modules = getattr(request, '_ttt_allowed_modules', None)
        if allowed_modules is None:
            allowed_modules = get_user_allowed_module_names(request.user)
            request._ttt_allowed_modules = allowed_modules

        is_admin = getattr(request, '_ttt_is_admin', None)
        if is_admin is None:
            is_admin = is_admin_user(request.user)
            request._ttt_is_admin = is_admin

        return {
            'is_admin': is_admin,
            'allowed_modules': allowed_modules,
            'session_cookie_age': session_cookie_age,
            # Hold/Release toggle on module pick tables. Any user who can open
            # a module page (enforced by ModuleAccessMiddleware) may hold or
            # release lots there; the hold/unhold APIs require authentication.
            'can_hold_release': True,
        }

    return {
        'is_admin': False,
        'allowed_modules': [],
        'session_cookie_age': session_cookie_age,
        'can_hold_release': False,
    }