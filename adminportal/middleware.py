import base64
from django.utils.crypto import get_random_string
from django.conf import settings
from django.http import HttpResponse, JsonResponse
import time
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# URL-prefix → set of module names that grant access to that area.
# Any module name from USER_CATEGORY_MODULES that belongs to the group
# mapped to the prefix gives the user access.
# ---------------------------------------------------------------------------
_MODULE_URL_MAP = {
    'dayplanning/':               {'Data Upload', 'DP Pick Table', 'DP Complete Table'},
    'inputscreening/':            {'Input Pick Table', 'Input Completed Table', 'Input Accept Table', 'Input Reject Table', 'Input Screening'},
    'recovery_dp/':               {'Recovery Data Upload', 'Recovery Pick Table', 'Recovery Completed Table'},
    'recovery_is/':               {'R-Pick Table', 'R-Completed Table', 'R-Accept Table', 'R-Reject Table'},
    'recovery_brassqc/':          {'R-Brass Qc Pick Table', 'R-Brass Qc Completed Table'},
    'recovery_brass_audit/':      {'R-Brass Audit Pick Table', 'R-Brass Audit Reject Table', 'R-Brass Audit Complete Table'},
    'recovery_iqf/':              {'R-IQF Pick Table', 'R-IQF Accept Table', 'R-IQF Reject Table', 'R-IQF Completed Table'},
    'brass_qc/':                  {'Brass Qc Pick Table', 'Brass Qc Completed Table'},
    'brass_audit/':               {'Brass Audit Pick Table', 'Brass Audit Complete Table', 'Brass Audit Reject Table'},
    'iqf/':                       {'IQF Pick Table', 'IQF Completed Table', 'IQF Accept Table', 'IQF Reject Table'},
    'jig_loading/':               {'Jig Pick Table', 'Jig Completed Table'},
    'jig_unloading/':             {'JUL Main Table', 'JUL Completed'},
    'JigUnloading_Zone2/':        {'JUL Main Table Zone 2', 'JUL Completed Zone 2'},
    'inprocess_inspection/':      {'IP Main', 'IP Completed'},
    'nickle_inspection/':         {'Nickel Main Table', 'Nickel Completed Table'},
    'nickle_inspection_zone_two/': {'Nickel Inspection Zone 2 Pick Table', 'Nickel Inspection Zone 2 Completed Table', 'Nickel Inspection Zone 2 Reject Table'},
    'nickel_audit/':              {'NA Pick Table', 'NA Completed'},
    'nickel_audit_zone_two/':     {'Nickel Audit Zone 2 Pick Table', 'Nickel Audit Zone 2 Completed Table'},
    'spider_spindle/':            {'Spider Spindle Z1 Pick Table', 'Spider Spindle Z1 Completed Table'},
    'spider_spindle_zone_two/':   {'Spider Spindle Z2 Pick Table', 'Spider Spindle Z2 Completed Table'},
}

_MODULE_ACCESS_DENIED_MSG = 'Module cannot be accessible. Contact admin to get the access.'

_MODULE_ACCESS_DENIED_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Access Restricted</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; background: #f1f5f9;
         display: flex; align-items: center; justify-content: center;
         min-height: 100vh; margin: 0; }}
  .card {{ background: #fff; border-radius: 12px; padding: 3rem 2.5rem;
           max-width: 480px; width: 100%; text-align: center;
           box-shadow: 0 4px 24px rgba(0,0,0,0.10); }}
  .icon {{ font-size: 3.5rem; margin-bottom: 1rem; }}
  h1 {{ color: #dc2626; font-size: 1.4rem; margin-bottom: 0.5rem; }}
  p  {{ color: #475569; font-size: 1rem; margin-bottom: 1.5rem; }}
  a  {{ display: inline-block; background: #2563eb; color: #fff;
        padding: 0.6rem 1.5rem; border-radius: 6px; text-decoration: none;
        font-weight: 600; }}
  a:hover {{ background: #1d4ed8; }}
</style>
</head>
<body>
<div class="card">
  <div class="icon">🔒</div>
  <h1>Access Restricted</h1>
  <p>{message}</p>
  <a href="/home/">Back to Dashboard</a>
</div>
</body>
</html>"""


class ModuleAccessMiddleware:
    """
    Intercepts requests to module URL prefixes and enforces that the
    authenticated user has at least one provisioned module for that area.

    - Unauthenticated users are passed through (login_required handles them).
    - Admin users are always allowed.
    - Non-HTML (API/JSON) requests receive a JSON 403.
    - HTML page requests receive a styled 403 page.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path.lstrip('/')

        # Determine which module group this URL belongs to.
        required_modules = None
        for prefix, modules in _MODULE_URL_MAP.items():
            if path.startswith(prefix):
                required_modules = modules
                break

        if required_modules is None:
            # Not a module URL — skip.
            return self.get_response(request)

        user = getattr(request, 'user', None)
        if user is None or not getattr(user, 'is_authenticated', False):
            # Not authenticated; let login_required redirect handle it.
            return self.get_response(request)

        # Lazy import to avoid circular imports at module load time.
        from adminportal.services import get_user_allowed_module_names, is_admin_user

        if is_admin_user(user):
            return self.get_response(request)

        allowed = set(get_user_allowed_module_names(user))
        if allowed.intersection(required_modules):
            return self.get_response(request)

        # Access denied.
        logger.warning(
            'MODULE_ACCESS_DENIED: user=%s path=%s required=%s',
            user.username,
            request.path,
            required_modules,
        )

        wants_json = (
            'application/json' in request.META.get('HTTP_ACCEPT', '')
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.path.rstrip('/').split('/')[-1].startswith('api')
        )
        if wants_json:
            return JsonResponse({'error': _MODULE_ACCESS_DENIED_MSG}, status=403)

        html = _MODULE_ACCESS_DENIED_HTML.format(message=_MODULE_ACCESS_DENIED_MSG)
        return HttpResponse(html, status=403, content_type='text/html; charset=utf-8')

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