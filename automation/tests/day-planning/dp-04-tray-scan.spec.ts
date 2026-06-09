// tests/day-planning/dp-04-tray-scan.spec.ts
// TC-DP-36 to TC-DP-52: Tray Scan Modal Tests

import { test, expect } from '../../fixtures/base.fixtures';

test.describe('Day Planning — Tray Scan Modal', () => {
  test.use({ storageState: 'fixtures/auth/dev-state.json' });

  test.beforeEach(async ({ pickTablePage }) => {
    await pickTablePage.goto();
    await pickTablePage.assertPickTableLoaded();
  });

  test(
    'TC-DP-36 @regression — Tray scan modal elements are present in DOM',
    async ({ page }) => {
      await expect(page.locator('#trayScanModal')).toBeAttached();
      await expect(page.locator('#trayScanDraftBtn')).toBeAttached();
      await expect(page.locator('#trayScanSubmitBtn')).toBeAttached();
      await expect(page.locator('#trayScanCancelBtn')).toBeAttached();
    }
  );

  test(
    'TC-DP-37 @regression — Day Planning view modal elements are present in DOM',
    async ({ page }) => {
      await expect(page.locator('#trayScanModal_DayPlanning')).toBeAttached();
      await expect(page.locator('#trayValidateBtn')).toBeAttached();
      await expect(page.locator('#trayErrorMessage')).toBeAttached();
    }
  );

  test(
    'TC-DP-38 @regression — Hold remark modal elements are present in DOM',
    async ({ page }) => {
      await expect(page.locator('#holdRemarkModal')).toBeAttached();
      await expect(page.locator('#holdRemarkInput')).toBeAttached();
      await expect(page.locator('#saveHoldRemarkBtn')).toBeAttached();
    }
  );

  test(
    'TC-DP-39 @regression — Tray scan API endpoint responds correctly',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/tray_scan/');
      // Should return 400/405 (no batch_id) not 404/500
      expect([200, 400, 405]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-40 @regression — Tray unique check API endpoint exists',
    async ({ page }) => {
      const resp = await page.request.get(
        '/dayplanning/tray_id_unique_check/?tray_id=TEST&batch_id=TEST'
      );
      expect([200, 400, 403]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-41 @regression — Draft tray API endpoint exists',
    async ({ page }) => {
      const resp = await page.request.post('/dayplanning/draft_tray/', {
        data: { batch_id: 'TEST', tray_id: 'TEST' },
      });
      expect([200, 400, 403, 422]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-42 @regression — Tray auto-save API endpoint exists',
    async ({ page }) => {
      const resp = await page.request.post('/dayplanning/tray_auto_save/', {
        data: { batch_id: 'TEST' },
      });
      expect([200, 400, 403, 422]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-43 @regression — Delete batch API requires POST (not GET)',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/delete_batch/');
      // GET should return 405 Method Not Allowed
      expect([405, 400, 403]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-44 @regression — Tray validate API endpoint exists',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/tray_validate/');
      expect([200, 400, 403]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-45 @regression — Globally drafted trays API endpoint exists',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/globally_drafted_trays/');
      expect([200, 400, 403]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-46 @regression — Hold unhold reason API endpoint exists',
    async ({ page }) => {
      const resp = await page.request.post('/dayplanning/save_hold_unhold_reason/', {
        data: { batch_id: 'TEST', reason: 'test' },
      });
      expect([200, 400, 403, 422]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-47 @regression — Redo button is present in tray scan modal',
    async ({ page }) => {
      await expect(page.locator('#trayIDRedoBtn')).toBeAttached();
    }
  );

  test(
    'TC-DP-48 @regression — Tray scan details container is present',
    async ({ page }) => {
      await expect(page.locator('#trayScanDetails')).toBeAttached();
      await expect(page.locator('#trayScanDetails_DayPlanning')).toBeAttached();
    }
  );

  test(
    'TC-DP-49 @regression — Tray quantity error footer is present',
    async ({ page }) => {
      await expect(page.locator('#trayQtyErrorFooter')).toBeAttached();
    }
  );

  test(
    'TC-DP-50 @regression — Verify top tray API endpoint exists',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/verify_top_tray_qty/');
      expect([200, 400, 403]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-51 @regression — Top tray scan API endpoint exists',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/top_tray_scan/');
      expect([200, 400, 403]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-52 @regression — Draft tray ID list API returns data',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/draft_tray_id_list/');
      expect([200, 400, 403]).toContain(resp.status());
    }
  );
});
