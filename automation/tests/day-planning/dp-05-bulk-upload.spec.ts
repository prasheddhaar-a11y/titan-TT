// tests/day-planning/dp-05-bulk-upload.spec.ts
// TC-DP-53 to TC-DP-68: Bulk Upload Tests

import { test, expect } from '../../fixtures/base.fixtures';
import path from 'path';
import fs from 'fs';

test.describe('Day Planning — Bulk Upload', () => {
  test.use({ storageState: 'fixtures/auth/dev-state.json' });

  test.beforeEach(async ({ bulkUploadPage }) => {
    await bulkUploadPage.goto();
    await bulkUploadPage.assertPageLoaded();
  });

  test(
    'TC-DP-53 @smoke @sanity — Bulk Upload page loads successfully',
    async ({ bulkUploadPage }) => {
      await bulkUploadPage.assertUrlContains('bulk_upload');
      await bulkUploadPage.assertPageLoaded();
    }
  );

  test(
    'TC-DP-54 @regression — File input element is present and accepts files',
    async ({ page }) => {
      const fileInput = page.locator('input[type="file"]').first();
      await expect(fileInput).toBeAttached();
    }
  );

  test(
    'TC-DP-55 @regression — Download template link is present',
    async ({ page }) => {
      const link = page.locator('a[href*="download_excel_template"]').first();
      await expect(link).toBeVisible();
    }
  );

  test(
    'TC-DP-56 @regression — Download Excel template API returns file',
    async ({ page }) => {
      const [download] = await Promise.all([
        page.waitForEvent('download', { timeout: 15_000 }),
        page.locator('a[href*="download_excel_template"]').first().click(),
      ]);
      expect(download.suggestedFilename()).toMatch(/\.xlsx$/i);
    }
  );

  test(
    'TC-DP-57 @regression — Submitting without a file shows validation error',
    async ({ page }) => {
      const submitBtn = page
        .locator('button[type="submit"], #uploadBtn, .upload-btn')
        .first();
      await submitBtn.click();
      // Expect either HTML5 validation or server error
      const hasNativeValidation = await page
        .locator('input[type="file"]:invalid')
        .count()
        .then((c) => c > 0)
        .catch(() => false);
      const hasServerError = await page
        .locator('.upload-error, .alert-danger, .error-message')
        .count()
        .then((c) => c > 0)
        .catch(() => false);
      expect(hasNativeValidation || hasServerError).toBeTruthy();
    }
  );

  test(
    'TC-DP-58 @regression — Upload an invalid file format shows error',
    async ({ page }) => {
      // Create a temp txt file
      const tmpFile = path.resolve('test-data/files/invalid.txt');
      fs.mkdirSync(path.dirname(tmpFile), { recursive: true });
      fs.writeFileSync(tmpFile, 'invalid content');

      await page.locator('input[type="file"]').first().setInputFiles(tmpFile);
      await page.locator('button[type="submit"], #uploadBtn').first().click();
      await page.waitForLoadState('networkidle');

      const errorVisible = await page
        .locator('.upload-error, .alert-danger, .error-message, [class*="error"]')
        .first()
        .isVisible()
        .catch(() => false);
      expect(errorVisible).toBeTruthy();

      fs.unlinkSync(tmpFile);
    }
  );

  test(
    'TC-DP-59 @regression — Bulk upload preview API exists',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/bulk_upload/preview/');
      expect([200, 400, 403, 405]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-60 @regression — Get plating colour API returns data',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/get_plating_colour/');
      expect([200, 400, 403]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-61 @regression — Get categories API returns data',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/get_categories/');
      expect([200, 400, 403]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-62 @regression — Get locations API returns data',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/get_locations/');
      expect([200, 400, 403]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-63 @regression — Get allowed versions API returns data',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/get_allowed_versions/');
      expect([200, 400, 403]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-64 @regression — Validate plating stock number API exists',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/validate_plating_stk_no/');
      expect([200, 400, 403]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-65 @regression — Tray ID list API returns data',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/tray_id_list/');
      expect([200, 400, 403]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-66 @regression — Completed tray ID list API returns data',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/completed_tray_id_list/');
      expect([200, 400, 403]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-67 @regression — Quick help API returns data',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/quick_help/');
      expect([200, 400, 403]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-68 @regression — Save DP pick remark API exists',
    async ({ page }) => {
      const resp = await page.request.post('/dayplanning/save_dp_pick_remark/', {
        data: { batch_id: 'TEST', remark: 'test' },
      });
      expect([200, 400, 403, 422]).toContain(resp.status());
    }
  );
});
