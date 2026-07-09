"""
End-to-end tests for the Microsoft SSO login flow.

Covers the regression where the callback logged the user in with
'django.contrib.auth.backends.ModelBackend' (not present in
AUTHENTICATION_BACKENDS), so django.contrib.auth.get_user() dropped the
session on the very next request and /home/ bounced back to the login page.

Microsoft's token endpoint is mocked; everything else (URLs, session,
middleware, views) runs for real.
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from urllib.parse import urlparse, parse_qs

User = get_user_model()


def _fake_msal_app(email, name='Kauvery Sree'):
    app = mock.MagicMock()
    app.get_authorization_request_url.side_effect = (
        lambda scopes, state, redirect_uri: f'https://login.microsoftonline.com/x?state={state}'
    )
    app.acquire_token_by_authorization_code.return_value = {
        'id_token_claims': {'preferred_username': email, 'name': name},
        'access_token': 'fake',
    }
    return app


class MicrosoftSSOLoginFlowTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST='localhost')

    def _do_sso_login(self, email):
        with mock.patch(
            'watchcase_tracker.sso.msal.ConfidentialClientApplication',
            return_value=_fake_msal_app(email),
        ):
            start = self.client.get('/auth/microsoft/login/')
            self.assertEqual(start.status_code, 302)
            state = parse_qs(urlparse(start['Location']).query)['state'][0]
            return self.client.get(f'/auth/microsoft/callback/?state={state}&code=FAKECODE')

    def test_sso_login_opens_dashboard_not_login_page(self):
        """After SSO the session must survive and /home/ must render (no bounce)."""
        User.objects.create_user(
            username='kauverysree@pinesphere.com',
            email='kauverysree@pinesphere.com',
            first_name='Kauvery',
            password='X',
            is_active=True,
        )
        cb = self._do_sso_login('kauverysree@pinesphere.com')
        self.assertEqual(cb.status_code, 302)
        self.assertEqual(cb['Location'], '/home/')

        # THE regression check: the next request must still be authenticated.
        home = self.client.get('/home/')
        self.assertEqual(
            home.status_code, 200,
            'SSO session was dropped — user bounced back to login page',
        )
        self.assertIn('allowed_modules', home.data)
        self.assertEqual(str(self.client.session.get('_auth_user_id')),
                         str(User.objects.get(email='kauverysree@pinesphere.com').id))
        # Session backend must be one Django will accept on later requests.
        from django.conf import settings
        self.assertIn(self.client.session['_auth_user_backend'],
                      settings.AUTHENTICATION_BACKENDS)
        self.assertTrue(self.client.session.get('mfa_verified'))

    def test_sso_admin_user_gets_all_modules(self):
        """Admin/superuser SSO login exposes the full module list on the dashboard."""
        User.objects.create_user(
            username='adminsso', email='admin@pinesphere.com',
            password='X', is_active=True, is_superuser=True,
        )
        cb = self._do_sso_login('admin@pinesphere.com')
        self.assertEqual(cb['Location'], '/home/')
        home = self.client.get('/home/')
        self.assertEqual(home.status_code, 200)
        self.assertGreater(len(home.data['allowed_modules']), 0)

    def test_sso_unknown_email_redirects_to_login_with_contact_admin_modal(self):
        cb = self._do_sso_login('stranger@nowhere.com')
        self.assertEqual(cb.status_code, 302)
        self.assertTrue(cb['Location'].startswith('/accounts/login'))
        login_page = self.client.get('/accounts/login/')
        self.assertContains(login_page, 'Contact Admin to access the portal')
        # Flag is one-shot: modal must not reappear on refresh.
        again = self.client.get('/accounts/login/')
        self.assertNotContains(again, 'Contact Admin to access the portal')

    def test_double_click_login_first_state_still_accepted(self):
        """Two login requests before the callback must not raise CSRF mismatch."""
        User.objects.create_user(
            username='dbl@pinesphere.com', email='dbl@pinesphere.com',
            password='X', is_active=True,
        )
        with mock.patch(
            'watchcase_tracker.sso.msal.ConfidentialClientApplication',
            return_value=_fake_msal_app('dbl@pinesphere.com'),
        ):
            s1 = parse_qs(urlparse(self.client.get('/auth/microsoft/login/')['Location']).query)['state'][0]
            self.client.get('/auth/microsoft/login/')  # second request overwrites legacy state
            cb = self.client.get(f'/auth/microsoft/callback/?state={s1}&code=FAKECODE')
        self.assertEqual(cb.status_code, 302)
        self.assertEqual(cb['Location'], '/home/')

    def test_callback_with_forged_state_rejected(self):
        self.client.get('/auth/microsoft/login/')
        resp = self.client.get('/auth/microsoft/callback/?state=forged&code=FAKECODE')
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b'State mismatch', resp.content)
