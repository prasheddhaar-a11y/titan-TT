from django.shortcuts import redirect
from django.conf import settings

class ForbiddenToLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Only redirect to login when the user is NOT authenticated.
        # Authenticated users who receive a 403 should stay on the 403 page
        # (e.g. module-access warning) rather than being looped through login.
        user = getattr(request, 'user', None)
        is_authenticated = getattr(user, 'is_authenticated', False)
        if (response.status_code == 403
                and not is_authenticated
                and not request.path.startswith(settings.LOGIN_URL)):
            return redirect(settings.LOGIN_URL + '?next=' + request.path)
        return response