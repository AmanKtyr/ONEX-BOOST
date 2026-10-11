"""
Session Expiry Middleware
=========================
When a Django session expires, `request.user` becomes AnonymousUser.
Without this middleware, `@login_required` redirects to the global LOGIN_URL
(now set to /login/), but AJAX requests and edge cases can still surface errors.

This middleware:
  - Skips public/static paths so they always render.
  - For any unauthenticated request to a protected page, shows a clear
    "session expired" message and redirects to the correct login page.
  - For AJAX / JSON requests, returns a 401 JSON response so the frontend
    can handle it gracefully.
"""

import json
import logging

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import Resolver404, resolve

logger = logging.getLogger(__name__)

# Paths that are always publicly accessible – no session required.
_PUBLIC_PREFIXES = (
    '/admin/',
    '/superadmin/login/',
    '/login/',
    '/logout/',
    '/sitemap.xml',
    '/robots.txt',
    '/static/',
    '/media/',
    '/whatsapp/webhook/',
    '/attendance/scan-attendance/',
)

# URL names that are always public (matched after resolve()).
_PUBLIC_URL_NAMES = frozenset({
    'index',
    'login',
    'superadmin_login',
    'logout',
    'terms_of_service',
    'privacy_policy',
    'refund_policy',
    'sitemap',
    'blogs',
    'blog_detail',
    'gym_software_lucknow',
    'how_to_start_gym',
    'bmi_calculator',
    'about',
    'features',
    'contact',
    'pricing',
    'contact_submission',
    'help',
    'password_reset_page',
})

# Also derive prefixes from settings to stay in sync with STATIC/MEDIA URLs.
def _get_public_prefixes():
    extra = []
    if hasattr(settings, 'STATIC_URL') and settings.STATIC_URL:
        extra.append(settings.STATIC_URL)
    if hasattr(settings, 'MEDIA_URL') and settings.MEDIA_URL:
        extra.append(settings.MEDIA_URL)
    return _PUBLIC_PREFIXES + tuple(extra)


def _is_ajax(request):
    """Detect AJAX / fetch requests that expect JSON back."""
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('Accept', '')
        or request.content_type == 'application/json'
    )


class SessionExpiredMiddleware:
    """
    Redirect unauthenticated users to the login page when their session
    expires, instead of letting Django show a 404 or a confusing error.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._public_prefixes = _get_public_prefixes()

    def __call__(self, request):
        # Enforce session inactivity timeout from SystemSetting for authenticated sessions
        if request.user.is_authenticated:
            try:
                from apps.superadmin.models import SystemSetting
                system_setting = SystemSetting.get_settings()
                if system_setting and system_setting.session_timeout_minutes:
                    timeout_seconds = int(system_setting.session_timeout_minutes) * 60
                    request.session.set_expiry(timeout_seconds)
            except Exception:
                pass
        else:
            # Only intervene for unauthenticated requests.
            if not self._is_public(request):
                logger.debug(
                    'SessionExpiredMiddleware: unauthenticated access to %s – redirecting to login.',
                    request.path,
                )
                if _is_ajax(request):
                    return JsonResponse(
                        {'error': 'session_expired', 'message': 'Your session has expired. Please log in again.'},
                        status=401,
                    )
                messages.warning(
                    request,
                    'Your session has expired. Please log in again.',
                )
                return redirect(settings.LOGIN_URL)

        return self.get_response(request)

    def _is_public(self, request):
        path = request.path_info

        # Fast prefix check.
        if any(path.startswith(prefix) for prefix in self._public_prefixes):
            return True

        # Resolve URL name for finer control.
        try:
            match = resolve(path)
            return match.url_name in _PUBLIC_URL_NAMES
        except Resolver404:
            # Unknown URL – let Django handle the 404 n ormally.
            return True
