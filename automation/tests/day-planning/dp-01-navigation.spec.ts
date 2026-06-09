// tests/day-planning/dp-01-navigation.spec.ts
// TC-DP-01 to TC-DP-05: Navigation Tests

import { test, expect } from '../../fixtures/base.fixtures';

test.describe('Day Planning — Navigation', () => {
  test.use({ storageState: 'fixtures/auth/dev-state.json' });

  test(
    'TC-DP-01 @smoke @sanity — Navigate to Day Planning Pick Table',
    async ({ pickTablePage }) => {
      await pickTablePage.goto();
      await pickTablePage.assertUrlContains('dayplanning/dp_pick_table');
      await pickTablePage.assertPickTableLoaded();
    }
  );

  test(
    'TC-DP-02 @smoke — Navigate to Day Planning Bulk Upload',
    async ({ bulkUploadPage }) => {
      await bulkUploadPage.goto();
      await bulkUploadPage.assertUrlContains('dayplanning/bulk_upload');
      await bulkUploadPage.assertPageLoaded();
    }
  );

  test(
    'TC-DP-03 @smoke — Navigate to Day Planning Completed Table',
    async ({ completedTablePage }) => {
      await completedTablePage.goto();
      await completedTablePage.assertUrlContains('dayplanning/dp_completed_table');
      await completedTablePage.assertCompletedTableLoaded();
    }
  );

  test(
    'TC-DP-04 @regression — Redirect unauthenticated user to login',
    async ({ page }) => {
      // Clear session and attempt direct navigation
      await page.context().clearCookies();
      await page.goto('/dayplanning/dp_pick_table/');
      await expect(page).toHaveURL(/login/, { timeout: 10_000 });
    }
  );

  test(
    'TC-DP-05 @regression — Page title is correct for Pick Table',
    async ({ pickTablePage }) => {
      await pickTablePage.goto();
      const title = await pickTablePage.getPageTitle();
      expect(title.toLowerCase()).toMatch(/day planning|ttt|track/i);
    }
  );
});
