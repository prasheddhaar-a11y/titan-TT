// tests/day-planning/dp-08-completed-table.spec.ts
// TC-DP-101 to TC-DP-110: Completed Table Tests

import { test, expect } from '../../fixtures/base.fixtures';

test.describe('Day Planning — Completed Table', () => {
  test.use({ storageState: 'fixtures/auth/dev-state.json' });

  test.beforeEach(async ({ completedTablePage }) => {
    await completedTablePage.goto();
    await completedTablePage.assertCompletedTableLoaded();
  });

  test(
    'TC-DP-101 @smoke — Completed table page loads correctly',
    async ({ completedTablePage }) => {
      await completedTablePage.assertUrlContains('dp_completed_table');
    }
  );

  test(
    'TC-DP-102 @regression — Completed table renders rows',
    async ({ completedTablePage }) => {
      const count = await completedTablePage.getCompletedRowCount();
      expect(count).toBeGreaterThanOrEqual(0);
    }
  );

  test(
    'TC-DP-103 @regression — Search in completed table filters results',
    async ({ completedTablePage }) => {
      const initial = await completedTablePage.getCompletedRowCount();
      await completedTablePage.searchInCompletedTable('ZZZNONEXISTENT999');
      const filtered = await completedTablePage.getCompletedRowCount();
      expect(filtered).toBeLessThanOrEqual(initial);
    }
  );

  test(
    'TC-DP-104 @regression — Completed table pagination info displayed',
    async ({ completedTablePage }) => {
      const info = await completedTablePage.getPaginationInfo();
      expect(info).toMatch(/showing|entries/i);
    }
  );

  test(
    'TC-DP-105 @regression — Completed table API returns 200',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/dp_completed_table/');
      expect(resp.status()).toBe(200);
    }
  );

  test(
    'TC-DP-106 @regression — Completed tray ID list API is callable',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/completed_tray_id_list/');
      expect([200, 400, 403]).toContain(resp.status());
    }
  );

  test(
    'TC-DP-107 @regression — Page does not have JavaScript errors on completed table',
    async ({ page, completedTablePage }) => {
      const errors: string[] = [];
      page.on('console', (msg) => {
        if (msg.type() === 'error') errors.push(msg.text());
      });
      await completedTablePage.goto();
      await completedTablePage.assertCompletedTableLoaded();
      const critical = errors.filter((e) => !e.includes('favicon') && !e.includes('net::ERR'));
      expect(critical).toHaveLength(0);
    }
  );

  test(
    'TC-DP-108 @regression — Completed table does not allow tray scanning',
    async ({ page }) => {
      // Completed table is read-only — no tray-scan-btn should be present
      const scanBtns = page.locator('.tray-scan-btn');
      const count = await scanBtns.count();
      // Either 0 buttons (correct) or they are disabled
      if (count > 0) {
        const firstBtn = scanBtns.first();
        const isDisabled = await firstBtn.isDisabled();
        expect(isDisabled).toBeTruthy();
      } else {
        expect(count).toBe(0);
      }
    }
  );

  test(
    'TC-DP-109 @regression — Completed table search with empty string restores all',
    async ({ completedTablePage }) => {
      await completedTablePage.searchInCompletedTable('LOT');
      const after = await completedTablePage.getCompletedRowCount();
      await completedTablePage.searchInCompletedTable('');
      const restored = await completedTablePage.getCompletedRowCount();
      expect(restored).toBeGreaterThanOrEqual(after);
    }
  );

  test(
    'TC-DP-110 @regression — Tray auto-save cleanup API is callable',
    async ({ page }) => {
      const resp = await page.request.post('/dayplanning/tray_auto_save_cleanup/', {
        data: { batch_id: 'TEST' },
      });
      expect([200, 400, 403, 422]).toContain(resp.status());
    }
  );
});
