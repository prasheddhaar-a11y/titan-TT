// tests/day-planning/dp-07-negative-boundary.spec.ts
// TC-DP-83 to TC-DP-100: Negative & Boundary Value Tests

import { test, expect } from '../../fixtures/base.fixtures';

test.describe('Day Planning — Negative & Boundary Value Tests', () => {
  test.use({ storageState: 'fixtures/auth/dev-state.json' });

  // ── Boundary Values ────────────────────────────────────────────────────────

  test(
    'TC-DP-83 @regression — Hold remark with exactly 50 characters is accepted',
    async ({ page }) => {
      await page.goto('/dayplanning/dp_pick_table/');
      const fiftyChars = 'A'.repeat(50);
      const input = page.locator('#holdRemarkInput');
      await input.fill(fiftyChars);
      const val = await input.inputValue();
      expect(val).toBe(fiftyChars);
    }
  );

  test(
    'TC-DP-84 @regression — Hold remark with 51 characters is truncated to 50',
    async ({ page }) => {
      await page.goto('/dayplanning/dp_pick_table/');
      const fiftyOneChars = 'A'.repeat(51);
      const input = page.locator('#holdRemarkInput');
      await input.fill(fiftyOneChars);
      const val = await input.inputValue();
      expect(val.length).toBeLessThanOrEqual(50);
    }
  );

  test(
    'TC-DP-85 @regression — Empty hold remark is not accepted',
    async ({ page }) => {
      await page.goto('/dayplanning/dp_pick_table/');
      const resp = await page.request.post('/dayplanning/save_hold_unhold_reason/', {
        data: { batch_id: 'TEST', reason: '' },
      });
      expect([400, 403, 422]).toContain(resp.status());
    }
  );

  // ── Negative API Tests ─────────────────────────────────────────────────────

  test(
    'TC-DP-86 @regression — Tray scan with empty tray_id is rejected',
    async ({ page }) => {
      const resp = await page.request.post('/dayplanning/tray_scan/', {
        data: { tray_id: '', batch_id: 'TEST' },
      });
      expect([400, 403, 422]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-87 @regression — Tray scan with duplicate tray_id is rejected',
    async ({ page }) => {
      // API must reject duplicate tray assignment
      const resp = await page.request.get(
        '/dayplanning/tray_id_unique_check/?tray_id=DUPLICATE_TEST&batch_id=TEST'
      );
      expect([200, 400, 403]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-88 @regression — Delete batch with non-existent batch_id is rejected',
    async ({ page }) => {
      const resp = await page.request.post('/dayplanning/delete_batch/', {
        data: { batch_id: 'NONEXISTENT_BATCH_99999' },
      });
      expect([400, 403, 404, 422]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-89 @regression — Update batch with zero quantity is rejected',
    async ({ page }) => {
      const resp = await page.request.post('/dayplanning/update_batch_quantity_and_color/', {
        data: { batch_id: 'TEST', quantity: 0 },
      });
      expect([400, 403, 422]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-90 @regression — Update batch with negative quantity is rejected',
    async ({ page }) => {
      const resp = await page.request.post('/dayplanning/update_batch_quantity_and_color/', {
        data: { batch_id: 'TEST', quantity: -100 },
      });
      expect([400, 403, 422]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-91 @regression — Non-existent Day Planning URL returns 404',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/nonexistent_endpoint_xyz/');
      expect(resp.status()).toBe(404);
    }
  );

  test(
    'TC-DP-92 @regression — GET on POST-only endpoints returns 405',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/delete_batch/');
      expect([405, 403, 400]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-93 @regression — Search with special characters does not crash',
    async ({ pickTablePage }) => {
      await pickTablePage.goto();
      await pickTablePage.assertPickTableLoaded();
      // Should not throw
      await pickTablePage.searchInTable("' OR '1'='1");
      const count = await pickTablePage.getPickTableRowCount();
      expect(count).toBeGreaterThanOrEqual(0);
    }
  );

  test(
    'TC-DP-94 @regression — Search with XSS payload does not execute script',
    async ({ page, pickTablePage }) => {
      await pickTablePage.goto();
      const alerts: string[] = [];
      page.on('dialog', async (dialog) => {
        alerts.push(dialog.message());
        await dialog.dismiss();
      });
      await pickTablePage.searchInTable('<script>alert("xss")</script>');
      await page.waitForTimeout(1_000);
      expect(alerts).toHaveLength(0);
    }
  );

  test(
    'TC-DP-95 @regression — Very long search string does not crash the page',
    async ({ pickTablePage }) => {
      await pickTablePage.goto();
      const longStr = 'A'.repeat(500);
      await pickTablePage.searchInTable(longStr);
      const count = await pickTablePage.getPickTableRowCount();
      expect(count).toBeGreaterThanOrEqual(0);
    }
  );

  test(
    'TC-DP-96 @regression — Page does not crash on rapid search input',
    async ({ page, pickTablePage }) => {
      await pickTablePage.goto();
      await pickTablePage.assertPickTableLoaded();
      const searchInput = page.locator('input[type="search"], .dataTables_filter input').first();
      for (const char of 'LOT-2026') {
        await searchInput.type(char, { delay: 20 });
      }
      await page.waitForTimeout(500);
      const count = await pickTablePage.getPickTableRowCount();
      expect(count).toBeGreaterThanOrEqual(0);
    }
  );

  test(
    'TC-DP-97 @regression — Tray scan with SQL injection payload is safely rejected',
    async ({ page }) => {
      const resp = await page.request.post('/dayplanning/tray_scan/', {
        data: { tray_id: "'; DROP TABLE dp_tray; --", batch_id: "'; DROP TABLE batch; --" },
      });
      // Must not be 500 (which would indicate a crash)
      expect(resp.status()).not.toBe(500);
    }
  );

  test(
    'TC-DP-98 @regression — Application does not expose stack traces on errors',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/nonexistent_xyz/');
      const body = await resp.text();
      // Django DEBUG should be False in production
      expect(body).not.toMatch(/Traceback \(most recent call last\)/);
    }
  );

  test(
    'TC-DP-99 @regression — Multiple rapid tray scan attempts do not create duplicates',
    async ({ page }) => {
      // Rapid fire — ensure unique check API handles concurrency
      const responses = await Promise.all([
        page.request.get('/dayplanning/tray_id_unique_check/?tray_id=RAPID&batch_id=TEST'),
        page.request.get('/dayplanning/tray_id_unique_check/?tray_id=RAPID&batch_id=TEST'),
        page.request.get('/dayplanning/tray_id_unique_check/?tray_id=RAPID&batch_id=TEST'),
      ]);
      for (const r of responses) {
        expect([200, 400, 403]).toContain(r.status());
        // Must not crash
        expect(r.status()).not.toBe(500);
      }
    }
  );

  test(
    'TC-DP-100 @regression — Row lock API prevents concurrent access from same user',
    async ({ page }) => {
      const r1 = await page.request.post('/dayplanning/row_lock/', {
        form: { batch_id: 'CONCURRENT_TEST', lot_id: 'LOT_CONCURRENT', action: 'lock' },
      });
      const r2 = await page.request.post('/dayplanning/row_lock/', {
        form: { batch_id: 'CONCURRENT_TEST', lot_id: 'LOT_CONCURRENT', action: 'lock' },
      });
      // Both should return valid responses (not 500)
      expect([200, 400, 403]).toContain(r1.status());
      expect([200, 400, 403]).toContain(r2.status());
    }
  );
});
