// fixtures/base.fixtures.ts
// Custom Playwright fixtures that inject Page Objects and shared state

import { test as base, Page } from '@playwright/test';
import { LoginPage } from '../pages/login.page';
import { DayPlanningPickTablePage } from '../pages/day-planning-pick-table.page';
import { DayPlanningBulkUploadPage } from '../pages/day-planning-bulk-upload.page';
import { DayPlanningCompletedTablePage } from '../pages/day-planning-completed-table.page';
import { ApiClient } from '../utils/api-client';
import { ENV } from '../config/environments';

// ─── Fixture Type Definitions ──────────────────────────────────────────────

export type PageFixtures = {
  loginPage: LoginPage;
  pickTablePage: DayPlanningPickTablePage;
  bulkUploadPage: DayPlanningBulkUploadPage;
  completedTablePage: DayPlanningCompletedTablePage;
  apiClient: ApiClient;
  authenticatedPage: Page;
};

// ─── Extended Test with Fixtures ──────────────────────────────────────────

export const test = base.extend<PageFixtures>({
  // Inject LoginPage
  loginPage: async ({ page }, use) => {
    await use(new LoginPage(page));
  },

  // Inject PickTablePage
  pickTablePage: async ({ page }, use) => {
    await use(new DayPlanningPickTablePage(page));
  },

  // Inject BulkUploadPage
  bulkUploadPage: async ({ page }, use) => {
    await use(new DayPlanningBulkUploadPage(page));
  },

  // Inject CompletedTablePage
  completedTablePage: async ({ page }, use) => {
    await use(new DayPlanningCompletedTablePage(page));
  },

  // Inject API Client
  apiClient: async ({ request }, use) => {
    await use(new ApiClient(request, ENV.baseUrl));
  },

  // Page already authenticated (uses storageState from config)
  authenticatedPage: async ({ page }, use) => {
    // storageState is loaded automatically from project config
    await use(page);
  },
});

export { expect } from '@playwright/test';
