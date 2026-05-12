from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from .services import _dashboard_cache_key, get_cached_dashboard_stats

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
