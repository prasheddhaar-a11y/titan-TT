// pages/day-planning-completed-table.page.ts
// Page Object for Day Planning Completed Table

import { Page, expect } from '@playwright/test';
import { BasePage } from './base.page';
import { DayPlanningCompletedTableLocators as L } from '../locators/day-planning.locators';
import { getTableRowCount } from '../utils/helpers';

export class DayPlanningCompletedTablePage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async goto(): Promise<void> {
    await this.navigate('/dayplanning/dp_completed_table/');
  }

  async getCompletedRowCount(): Promise<number> {
    return getTableRowCount(this.page, L.completedTable);
  }

  async searchInCompletedTable(term: string): Promise<void> {
    await this.fill(L.searchInput, term);
    await this.page.waitForTimeout(500);
  }

  async clickNextPage(): Promise<void> {
    await this.click(L.paginationNext);
    await this.page.waitForTimeout(500);
  }

  async assertCompletedTableLoaded(): Promise<void> {
    await expect(this.page.locator(L.completedTable)).toBeVisible({ timeout: 15_000 });
    this.log.pass('Completed table loaded');
  }

  async getPaginationInfo(): Promise<string> {
    return this.getText(L.paginationInfo);
  }
}
