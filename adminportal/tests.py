from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from .models import UserActiveSession
from .services import _dashboard_cache_key, get_active_session_conflict_message, get_cached_dashboard_stats

@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'adminportal-dashboard-tests',
        }
    }
)
class DashboardStatsCacheTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_cache_only_mode_does_not_calculate_on_miss(self):
        with patch('adminportal.services.get_dashboard_stats_for_labels') as mocked_stats:
            stats = get_cached_dashboard_stats(
                allowed_module_names=['Data Upload'],
                calculate_on_miss=False,
            )

        self.assertEqual(stats, [])
        mocked_stats.assert_not_called()

    def test_cache_only_mode_returns_available_cached_stats(self):
        cached_stat = {
            'label': 'Day Planning',
            'total_lot': 5,
            'display_stats': [{'label': 'Total Batches', 'value': 5}],
        }
        cache.set(_dashboard_cache_key('Day Planning'), cached_stat, timeout=60)

        with patch('adminportal.services.get_dashboard_stats_for_labels') as mocked_stats:
            stats = get_cached_dashboard_stats(
                allowed_module_names=['Data Upload'],
                calculate_on_miss=False,
            )

        self.assertEqual(stats, [cached_stat])
        mocked_stats.assert_not_called()

    def test_cache_only_mode_skips_stale_cached_stats(self):
        cache.set(_dashboard_cache_key('Day Planning'), {'label': 'Day Planning'}, timeout=60)

        with patch('adminportal.services.get_dashboard_stats_for_labels') as mocked_stats:
            stats = get_cached_dashboard_stats(
                allowed_module_names=['Data Upload'],
                calculate_on_miss=False,
            )

        self.assertEqual(stats, [])
        mocked_stats.assert_not_called()


class ActiveSessionConflictMessageTests(TestCase):
    """
    Regression coverage for the false-positive "already active on another
    device" block on a genuinely first-ever login: login() always cycles the
    session key, so the pre-login anonymous key can never equal the
    just-created active session's key, even for the same tab. IP+User-Agent
    is the fallback signal that distinguishes a same-device retry (double
    submit / retried request) from an actual second device.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='racer', password='X')
        self.factory = RequestFactory()
        Session.objects.create(
            session_key='freshly-cycled-key',
            session_data='',
            expire_date=timezone.now() + timedelta(minutes=15),
        )
        UserActiveSession.objects.create(
            user=self.user,
            session_key='freshly-cycled-key',
            ip_address='10.0.0.5',
            user_agent='TestBrowser/1.0',
            updated_at=timezone.now(),
        )

    def _request(self, ip='10.0.0.5', ua='TestBrowser/1.0'):
        req = self.factory.post('/accounts/login/')
        req.META['REMOTE_ADDR'] = ip
        req.META['HTTP_USER_AGENT'] = ua
        return req

    def test_same_device_double_submit_is_not_blocked(self):
        """Matching IP+UA (same browser retrying) must not be treated as a conflict."""
        message = get_active_session_conflict_message(
            self.user, current_session_key='pre-login-anon-key', request=self._request(),
        )
        self.assertIsNone(message)

    def test_different_device_is_still_blocked(self):
        """A different IP/User-Agent is a genuine second device and must still be rejected."""
        message = get_active_session_conflict_message(
            self.user,
            current_session_key='pre-login-anon-key',
            request=self._request(ip='203.0.113.9', ua='OtherBrowser/9.0'),
        )
        self.assertIsNotNone(message)

    def test_no_request_falls_back_to_prior_strict_behavior(self):
        """Without a request (e.g. non-HTTP callers), behavior is unchanged."""
        message = get_active_session_conflict_message(self.user, current_session_key='pre-login-anon-key')
        self.assertIsNotNone(message)
