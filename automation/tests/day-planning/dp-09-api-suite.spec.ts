// tests/day-planning/dp-09-api-suite.spec.ts
// TC-DP-111 to TC-DP-125: Comprehensive API Test Suite

import { test, expect } from '../../fixtures/base.fixtures';

test.describe('Day Planning — API Test Suite', () => {
  test.use({ storageState: 'fixtures/auth/dev-state.json' });

  // Complete API endpoint coverage
  const endpoints: Array<{ name: string; method: 'GET' | 'POST'; url: string }> = [
    { name: 'dp_pick_table', method: 'GET', url: '/dayplanning/dp_pick_table/' },
    { name: 'dp_completed_table', method: 'GET', url: '/dayplanning/dp_completed_table/' },
    { name: 'bulk_upload', method: 'GET', url: '/dayplanning/bulk_upload/' },
    { name: 'get_plating_colour', method: 'GET', url: '/dayplanning/get_plating_colour/' },
    { name: 'get_categories', method: 'GET', url: '/dayplanning/get_categories/' },
    { name: 'get_locations', method: 'GET', url: '/dayplanning/get_locations/' },
    { name: 'get_allowed_versions', method: 'GET', url: '/dayplanning/get_allowed_versions/' },
    { name: 'get_plating_colors', method: 'GET', url: '/dayplanning/get_plating_colors/' },
    { name: 'tray_id_list', method: 'GET', url: '/dayplanning/tray_id_list/' },
    { name: 'draft_tray_id_list', method: 'GET', url: '/dayplanning/draft_tray_id_list/' },
    { name: 'globally_drafted_trays', method: 'GET', url: '/dayplanning/globally_drafted_trays/' },
    { name: 'completed_tray_id_list', method: 'GET', url: '/dayplanning/completed_tray_id_list/' },
    { name: 'quick_help', method: 'GET', url: '/dayplanning/quick_help/' },
    { name: 'row_lock_check', method: 'GET', url: '/dayplanning/row_lock/check/' },
    { name: 'download_excel_template', method: 'GET', url: '/dayplanning/download_excel_template/' },
  ];

  for (const ep of endpoints) {
    test(`TC-API — ${ep.name} endpoint is reachable`, async ({ page }) => {
      const resp = ep.method === 'GET'
        ? await page.request.get(ep.url)
        : await page.request.post(ep.url, { data: {} });

      // Must not be 404 (endpoint must exist) or 500 (must not crash)
      expect(resp.status()).not.toBe(404);
      expect(resp.status()).not.toBe(500);
    });
  }

  test(
    'TC-DP-111 @regression — No API endpoint returns 500 status',
    async ({ page }) => {
      const getEndpoints = [
        '/dayplanning/dp_pick_table/',
        '/dayplanning/dp_completed_table/',
        '/dayplanning/bulk_upload/',
        '/dayplanning/get_plating_colour/',
        '/dayplanning/get_categories/',
        '/dayplanning/get_locations/',
        '/dayplanning/quick_help/',
      ];
      for (const url of getEndpoints) {
        const resp = await page.request.get(url);
        expect(resp.status(), `Expected non-500 for ${url}`).not.toBe(500);
      }
    }
  );
});
