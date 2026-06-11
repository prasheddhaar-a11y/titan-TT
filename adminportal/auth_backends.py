"""
Authentication backend enforcing the account lockout policy.

Security fix: Missing Account Lockout Policy.
Extends Django's ModelBackend so existing username/password authentication
behaviour is unchanged, except:
  - A locked account can never authenticate, even with the correct password.
  - Every failed password attempt for an existing user increments the
    consecutive-failure counter (account locks at the threshold).
  - A successful login resets the counter.

Enforcing this at the backend level covers every password-based login path:
the HTML login form (TimedLoginView), LoginAPIView, swap-login verification
and the Django admin login.
"""
import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied

security_logger = logging.getLogger('security.auth')


class AccountLockoutBackend(ModelBackend):

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None

        # Imported lazily to avoid app-registry issues at startup.
        from .services import (
            is_user_account_locked,
            record_failed_login_attempt,
            reset_failed_login_attempts,
        )

        target_user = UserModel.objects.filter(username=username).first()

        if target_user is not None and is_user_account_locked(target_user):
            security_logger.warning(
                'LOGIN_BLOCKED_LOCKED_ACCOUNT: user=%s ip=%s',
                username,
                request.META.get('REMOTE_ADDR', 'unknown') if request is not None else 'unknown',
            )
            # PermissionDenied makes django.contrib.auth.authenticate() fail
            # immediately without trying other backends or checking the password.
            raise PermissionDenied('Account is locked.')

        user = super().authenticate(request, username=username, password=password, **kwargs)

        if user is not None:
            reset_failed_login_attempts(user)
        elif target_user is not None:
            record_failed_login_attempt(target_user, request=request)

        return user
