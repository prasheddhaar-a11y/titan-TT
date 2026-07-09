import importlib
import os
from unittest import TestCase

from django.contrib.auth import get_user_model
from django.test import RequestFactory

from watchcase_tracker.sso import _get_redirect_uri, _resolve_local_user_for_sso


class MicrosoftRedirectUriTests(TestCase):
    def test_settings_loads_redirect_uri_base_from_project_dotenv(self):
        import watchcase_tracker.settings as settings_module

        os.environ.pop('MSAL_REDIRECT_URI_BASE', None)
        reloaded = importlib.reload(settings_module)

        self.assertEqual(reloaded.MSAL_REDIRECT_URI_BASE, 'http://localhost:8000')

        importlib.reload(settings_module)

    def test_resolver_matches_existing_user_by_username_local_part(self):
        User = get_user_model()
        existing = User.objects.create_user(
            username='kauvery',
            email='other@example.com',
            password='TempPass123!',
            is_active=True,
        )

        resolved = _resolve_local_user_for_sso('kauvery@example.com')

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.id, existing.id)

    def test_redirect_uri_is_built_from_named_callback_route(self):
        request = RequestFactory().get('/accounts/login/')
        request.META['SERVER_NAME'] = 'localhost'
        request.META['SERVER_PORT'] = '8000'
        redirect_uri = _get_redirect_uri(request)

        self.assertTrue(redirect_uri.endswith('/auth/microsoft/callback/'))
        self.assertIn('http://localhost:8000', redirect_uri)
