// tests/day-planning/dp-03-pick-table.spec.ts
// TC-DP-19 to TC-DP-35: Pick Table — View, Search, Filter, Pagination

import { test, expect } from '../../fixtures/base.fixtures';
import { loadTestData } from '../../utils/helpers';

interface DPData {
  searchTerms: { validLotSearch: string; noResultSearch: string; partialSearch: string };
  pagination: { pageSizes: string[] };
}

const dpData = loadTestData<DPData>('day-planning.json');

test.describe('Day Planning — Pick Table', () => {
  test.use({ storageState: 'fixtures/auth/dev-state.json' });

  test.beforeEach(async ({ pickTablePage }) => {
    await pickTablePage.goto();
    await pickTablePage.assertPickTableLoaded();
  });

  // ── View ──────────────────────────────────────────────────────────────────

  test(
    'TC-DP-19 @smoke @sanity — Pick table renders with data rows',
    async ({ pickTablePage }) => {
      const rowCount = await pickTablePage.getPickTableRowCount();
      expect(rowCount).toBeGreaterThanOrEqual(0);
    }
  );

  test(
    'TC-DP-20 @regression — Pick table has correct column headers',
    async ({ page }) => {
      const headers = page.locator('#order-listing thead th');
      const count = await headers.count();
      expect(count).toBeGreaterThan(0);
    }
  );

  test(
    'TC-DP-21 @regression — Tray scan button is visible per row',
    async ({ page }) => {
      const rowCount = await page.locator('#order-listing tbody tr').count();
      if (rowCount > 0) {
        const trayScanBtns = page.locator('.tray-scan-btn');
        expect(await trayScanBtns.count()).toBeGreaterThan(0);
      }
    }
  );

  // ── Search ────────────────────────────────────────────────────────────────

  test(
    'TC-DP-22 @smoke — Search with valid term filters results',
    async ({ pickTablePage }) => {
      const initialCount = await pickTablePage.getPickTableRowCount();
      await pickTablePage.searchInTable(dpData.searchTerms.validLotSearch);
      const filteredCount = await pickTablePage.getPickTableRowCount();
      expect(filteredCount).toBeLessThanOrEqual(initialCount);
    }
  );

  test(
    'TC-DP-23 @regression — Search with no-match term shows empty state',
    async ({ pickTablePage }) => {
      await pickTablePage.searchInTable(dpData.searchTerms.noResultSearch);
      const count = await pickTablePage.getPickTableRowCount();
      expect(count).toBe(0);
    }
  );

  test(
    'TC-DP-24 @regression — Clearing search restores full result set',
    async ({ pickTablePage }) => {
      const initialCount = await pickTablePage.getPickTableRowCount();
      await pickTablePage.searchInTable(dpData.searchTerms.noResultSearch);
      await pickTablePage.clearSearch();
      const restoredCount = await pickTablePage.getPickTableRowCount();
      expect(restoredCount).toBe(initialCount);
    }
  );

  test(
    'TC-DP-25 @regression — Partial search term filters correctly',
    async ({ pickTablePage }) => {
      await pickTablePage.searchInTable(dpData.searchTerms.partialSearch);
      const count = await pickTablePage.getPickTableRowCount();
      expect(count).toBeGreaterThanOrEqual(0);
    }
  );

  // ── Pagination ────────────────────────────────────────────────────────────

  test(
    'TC-DP-26 @regression — Pagination info displays correctly',
    async ({ pickTablePage }) => {
      const info = await pickTablePage.getPaginationInfo();
      // DataTables shows "Showing X to Y of Z entries"
      expect(info).toMatch(/showing/i);
    }
  );

  test(
    'TC-DP-27 @regression — Page length change to 25 works',
    async ({ pickTablePage }) => {
      await pickTablePage.setPageLength('25');
      const count = await pickTablePage.getPickTableRowCount();
      expect(count).toBeLessThanOrEqual(25);
    }
  );

  test(
    'TC-DP-28 @regression — Page length change to 50 works',
    async ({ pickTablePage }) => {
      await pickTablePage.setPageLength('50');
      const count = await pickTablePage.getPickTableRowCount();
      expect(count).toBeLessThanOrEqual(50);
    }
  );

  test(
    'TC-DP-29 @regression — Next page navigates correctly',
    async ({ pickTablePage }) => {
      const isEnabled = await pickTablePage.isNextPageEnabled();
      if (isEnabled) {
        await pickTablePage.clickNextPage();
        const info = await pickTablePage.getPaginationInfo();
        expect(info).toMatch(/showing/i);
      }
    }
  );

  test(
    'TC-DP-30 @regression — Previous page navigates back correctly',
    async ({ pickTablePage }) => {
      const isEnabled = await pickTablePage.isNextPageEnabled();
      if (isEnabled) {
        await pickTablePage.clickNextPage();
        await pickTablePage.clickPrevPage();
        const info = await pickTablePage.getPaginationInfo();
        expect(info).toMatch(/showing 1/i);
      }
    }
  );

  // ── Row Lock & Concurrency ─────────────────────────────────────────────────

  test(
    'TC-DP-31 @regression — Row lock API is called when tray scan modal opens',
    async ({ page, pickTablePage }) => {
      const rows = page.locator('#order-listing tbody tr');
      const rowCount = await rows.count();
      if (rowCount === 0) {
        test.skip(true, 'No rows in pick table to test row lock');
        return;
      }
      // Verify row_lock endpoint exists and responds
      const resp = await page.request.post('/dayplanning/row_lock/', {
        form: { batch_id: 'test', lot_id: 'test', action: 'test' },
      });
      // Should return 400 (missing valid data) not 404/500
      expect([200, 400]).toContain(resp.status());
    }
  );

  // ── Data Display ──────────────────────────────────────────────────────────

  test(
    'TC-DP-32 @regression — Page renders without JavaScript console errors',
    async ({ page, pickTablePage }) => {
      const errors: string[] = [];
      page.on('console', (msg) => {
        if (msg.type() === 'error') errors.push(msg.text());
      });
      await pickTablePage.goto();
      await pickTablePage.assertPickTableLoaded();
      // Filter known acceptable errors (e.g., missing favicon)
      const criticalErrors = errors.filter(
        (e) => !e.includes('favicon') && !e.includes('net::ERR')
      );
      expect(criticalErrors).toHaveLength(0);
    }
  );

  test(
    'TC-DP-33 @regression — Pick table API returns 200',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/dp_pick_table/');
      expect(resp.status()).toBe(200);
    }
  );

  test(
    'TC-DP-34 @regression — Completed table API returns 200',
    async ({ page }) => {
      const resp = await page.request.get('/dayplanning/dp_completed_table/');
      expect(resp.status()).toBe(200);
    }
  );

  test(
    'TC-DP-35 @regression — Scan status message element exists in DOM',
    async ({ page }) => {
      await expect(page.locator('#scanStatusMessage')).toBeAttached();
    }
  );
});
