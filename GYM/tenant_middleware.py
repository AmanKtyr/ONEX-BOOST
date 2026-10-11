import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import Resolver404, resolve

from apps.superadmin.models import Gym

logger = logging.getLogger(__name__)

PUBLIC_URL_NAMES = frozenset(
    {
        'index',
        'login',
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
        'who_we_are',
        'our_story',
        'leadership',
        'features',
        'contact',
        'pricing',
        'contact_submission',
        'public_diet_plan',
        'public_workout_plan',
        'help',
    }
)
PUBLIC_ROUTE_NAMES = frozenset(
    {
        (None, url_name) for url_name in PUBLIC_URL_NAMES
    }
    | {
        ('events', 'event_registration'),
    }
)


class TenantMiddleware:
    PUBLIC_PATH_PREFIXES = tuple(
        prefix
        for prefix in (
            '/admin/',
            '/superadmin/',
            '/accounts/',
            '/notifications/',
            '/whatsapp/webhook/',
            '/attendance/scan-attendance/',
            settings.STATIC_URL,
            settings.MEDIA_URL,
        )
        if prefix
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.gym = None

        if self._is_public_request(request):
            return self.get_response(request)

        if request.session.get('role') == 'superadmin':
            return self.get_response(request)

        gym_id = request.session.get('gym_id')
        if not gym_id:
            return redirect('login')

        gym = self._get_gym(gym_id)
        if gym is None:
            self._clear_tenant_session(request)
            return redirect('login')

        if gym.is_frozen:
            self._handle_frozen_gym(request, gym)
            return redirect('login')

        request.gym = gym
        return self.get_response(request)

    def _is_public_request(self, request):
        path = request.path_info

        if any(path.startswith(prefix) for prefix in self.PUBLIC_PATH_PREFIXES):
            return True

        try:
            match = resolve(path)
        except Resolver404:
            return False

        namespace = match.namespace or None
        return (namespace, match.url_name) in PUBLIC_ROUTE_NAMES

    def _get_gym(self, gym_id):
        try:
            return Gym.objects.get(id=gym_id)
        except Gym.DoesNotExist:
            logger.warning('Gym not found for tenant session gym_id=%s', gym_id)
            return None

    def _clear_tenant_session(self, request):
        for key in ('gym_id', 'gym_name', 'gym_logo', 'gym_phone', 'role'):
            request.session.pop(key, None)

    def _handle_frozen_gym(self, request, gym):
        logger.info('Blocked access for frozen gym id=%s name=%s', gym.id, gym.name)
        logout(request)
        messages.error(
            request,
            'Your gym account has been frozen. Please contact support for assistance.',
        )
