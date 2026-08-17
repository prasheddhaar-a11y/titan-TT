"""
Centralized normal-user UI/action fixes.

This file contains module-specific rules for normal users.
Currently only Day Planning / DP Pick Table is enabled.

Do not put general authentication or module-access logic here.
"""

NORMAL_USER_FIXES = {
    "Day Planning": {
        "DP Pick Table": {
            "edit": True,
            "delete": False,
        },
    },
}


def is_normal_user(user):
    """
    Return True when the authenticated user is not an administrator.

    Existing project authentication/module-access logic remains
    responsible for deciding which modules the user can access.
    """
    if not getattr(user, "is_authenticated", False):
        return False

    return not (
        getattr(user, "is_superuser", False)
        or user.groups.filter(name__iexact="Admin").exists()
    )


def get_normal_user_fix_config(user, module, page):
    """
    Return the UI/action rules for a normal user on a specific page.
    """
    if not is_normal_user(user):
        return {}

    return (
        NORMAL_USER_FIXES
        .get(module, {})
        .get(page, {})
        .copy()
    )