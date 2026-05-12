import base64
from django.utils.crypto import get_random_string
from django.conf import settings
import time
import logging

logger = logging.getLogger(__name__)

class CSPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        nonce = base64.b64encode(get_random_string(16).encode()).decode()
        request.csp_nonce = nonce
        response = self.get_response(request)
        response['Content-Security-Policy'] = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}' https://unpkg.com https://cdn.jsdelivr.net/npm/sweetalert2@11 'strict-dynamic';"
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
            "font-src 'self' https://*.lottiefiles.com https://fonts.gstatic.com https://cdnjs.cloudflare.com https://demo.bootstrapdash.com;"
            "img-src 'self' https://assets2.lottiefiles.com/packages/lf20_uiyqFZ.json https://assets10.lottiefiles.com/packages/lf20_jcikwtux.json https://demo.bootstrapdash.com/skydash/themes/assets/images/logo-mini.svg https://demo.bootstrapdash.com/skydash/themes/assets/images/logo.svg https://demo.bootstrapdash.com/skydash/themes/assets/images/dashboard/people.svg data:; "
            "connect-src 'self' https://assets2.lottiefiles.com/packages/lf20_uiyqFZ.json https://assets10.lottiefiles.com/packages/lf20_jcikwtux.json;"            
            "frame-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self';"
        )
        return response


class LoginLatencyMiddleware:
    """
    Middleware to measure login flow latency.
    Logs timing for authentication, dashboard stats, and response rendering.
    Only active for login-related paths.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only profile login-related endpoints
        if request.path not in ('/', '/home/') and 'login' not in request.path and 'index' not in request.path:
            return self.get_response(request)

        request.start_time = time.time()
        request.timers = {}
        
        response = self.get_response(request)
        
        # Log total time
        total_time = (time.time() - request.start_time) * 1000  # Convert to ms
        
        timer_log = ' | '.join([f'{k}={v}' for k, v in request.timers.items()])
        if getattr(settings, 'ENABLE_LOGIN_LATENCY_LOGS', False):
            logger.warning(
                f'LOGIN_LATENCY: {request.path} | '
                f'Total={total_time:.2f}ms | {timer_log}'
            )
        
        # Add header with timing for debugging
        response['X-Login-Total-Time'] = f'{total_time:.2f}ms'
        for k, v in request.timers.items():
            response[f'X-Login-{k.upper()}'] = v
        
        return response