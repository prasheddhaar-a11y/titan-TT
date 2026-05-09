from adminportal.services import get_user_allowed_module_names, is_admin_user


def user_permissions(request):
    """Add user permission context to all templates.
    """
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
        }

    return {
        'is_admin': False,
        'allowed_modules': [],
    }