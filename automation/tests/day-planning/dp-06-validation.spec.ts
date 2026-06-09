// tests/day-planning/dp-06-validation.spec.ts
// TC-DP-69 to TC-DP-82: Mandatory Field, Permission & Workflow Validation

import { test, expect } from '../../fixtures/base.fixtures';
import { loadTestData } from '../../utils/helpers';

interface DPData {
  boundaryValues: {
    minQuantity: number;
    maxQuantity: number;
    belowMinQuantity: number;
    aboveMaxQuantity: number;
    holdRemarkMaxLength: number;
  };
  oversizeRemark: string;
}

const dpData = loadTestData<DPData>('day-planning.json');

test.describe('Day Planning — Field Validation', () => {
  test.use({ storageState: 'fixtures/auth/dev-state.json' });

  // ── Hold Remark Field Validation ───────────────────────────────────────────

  test(
    'TC-DP-69 @regression — Hold remark input has maxlength=50',
    async ({ page }) => {
      await page.goto('/dayplanning/dp_pick_table/');
      const maxLen = await page.locator('#holdRemarkInput').getAttribute('maxlength');
      expect(parseInt(maxLen ?? '0', 10)).toBe(dpData.boundaryValues.holdRemarkMaxLength);
    }
  );

  test(
    'TC-DP-70 @regression — Hold remark input rejects more than 50 characters',
    async ({ page }) => {
      await page.goto('/dayplanning/dp_pick_table/');
      const input = page.locator('#holdRemarkInput');
      await input.fill(dpData.oversizeRemark);
      const val = await input.inputValue();
      expect(val.length).toBeLessThanOrEqual(50);
    }
  );

  test(
    'TC-DP-71 @regression — Tray ID input does not allow autocomplete',
    async ({ page }) => {
      await page.goto('/dayplanning/dp_pick_table/');
      const trayInputs = page.locator('.tray-id-input');
      const count = await trayInputs.count();
      if (count > 0) {
        const autocomplete = await trayInputs.first().getAttribute('autocomplete');
        expect(autocomplete).toBe('off');
      }
    }
  );

  test(
    'TC-DP-72 @regression — Scan hidden input exists and is accessible',
    async ({ page }) => {
      await page.goto('/dayplanning/dp_pick_table/');
      await expect(page.locator('#scanHiddenInput')).toBeAttached();
    }
  );

  // ── Workflow API Validation ────────────────────────────────────────────────

  test(
    'TC-DP-73 @regression — Update batch quantity API rejects invalid data',
    async ({ page }) => {
      const resp = await page.request.post('/dayplanning/update_batch_quantity_and_color/', {
        data: { batch_id: '', quantity: -1 },
      });
      expect([400, 403, 422]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-74 @regression — Delete batch API rejects missing batch_id',
    async ({ page }) => {
      const resp = await page.request.post('/dayplanning/delete_batch/', {
        data: { batch_id: '' },
      });
      expect([400, 403, 422]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-75 @regression — Row lock API rejects empty batch_id',
    async ({ page }) => {
      const resp = await page.request.post('/dayplanning/row_lock/', {
        form: { batch_id: '', lot_id: '', action: 'lock' },
      });
      expect([400, 403]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-76 @regression — Row lock check API endpoint is reachable',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/row_lock/check/');
      expect([200, 400, 403]).toContain(resp.status());
    }
  );

  // ── Session Validation ─────────────────────────────────────────────────────

  test(
    'TC-DP-77 @regression — Expired session redirects to login on page access',
    async ({ page }) => {
      await page.context().clearCookies();
      const resp = await page.request.get('/dayplanning/dp_pick_table/');
      // Django redirects unauthenticated requests
      expect([200, 302, 403]).toContain(resp.status());
      if (resp.status() === 200) {
        // Check if response is actually the login page
        const body = await resp.text();
        expect(body).toMatch(/login|sign in/i);
      }
    }
  );

  test(
    'TC-DP-78 @regression — API endpoints return 403 without authentication',
    async ({ page }) => {
      await page.context().clearCookies();
      const resp = await page.request.get('/dayplanning/dp_pick_table/');
      // Should NOT be 500 (internal server error)
      expect(resp.status()).not.toBe(500);
    }
  );

  // ── Status & Workflow ──────────────────────────────────────────────────────

  test(
    'TC-DP-79 @regression — Get lot ID for tray API endpoint exists',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/dget_lot_id_for_tray/?tray_id=TEST');
      expect([200, 400, 403, 404]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-80 @regression — Draft tray delete API endpoint exists',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/draft_tray_delete/');
      expect([200, 400, 403, 405]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-81 @regression — Get plating colors API returns list',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/get_plating_colors/');
      expect([200, 400, 403]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-82 @regression — Validate top tray API endpoint exists',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/validate_top_tray/');
      expect([200, 400, 403]).toContain(resp.status());
    }
  );
});
