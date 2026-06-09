// pages/day-planning-pick-table.page.ts
// Page Object for Day Planning Pick Table

import { Page, expect } from '@playwright/test';
import { BasePage } from './base.page';
import { DayPlanningPickTableLocators as L } from '../locators/day-planning.locators';
import { waitForApiResponse, getTableRowCount, getColumnValues } from '../utils/helpers';

export class DayPlanningPickTablePage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  // ─── Navigation ────────────────────────────────────────────────────────────

  async goto(): Promise<void> {
    await this.navigate('/dayplanning/dp_pick_table/');
  }

  // ─── Table ─────────────────────────────────────────────────────────────────

  async getPickTableRowCount(): Promise<number> {
    return getTableRowCount(this.page, L.pickTable);
  }

  async getRowByIndex(index: number) {
    return this.page.locator(L.pickTableRows).nth(index);
  }

  async getAllLotIds(): Promise<string[]> {
    // Lot ID is typically column 2 (index 1) in the pick table
    return getColumnValues(this.page, L.pickTable, 1);
  }

  async assertPickTableLoaded(): Promise<void> {
    await expect(this.page.locator(L.pickTable)).toBeVisible({ timeout: 15_000 });
    this.log.pass('Pick table is loaded');
  }

  // ─── Search ────────────────────────────────────────────────────────────────

  async searchInTable(searchTerm: string): Promise<void> {
    this.log.step(`Search pick table: "${searchTerm}"`);
    await this.fill(L.searchInput, searchTerm);
    await this.page.waitForTimeout(500); // Allow DataTables to filter
  }

  async clearSearch(): Promise<void> {
    await this.fill(L.searchInput, '');
    await this.page.waitForTimeout(300);
  }

  async getSearchResultCount(): Promise<number> {
    return getTableRowCount(this.page, L.pickTable);
  }

  // ─── Pagination ────────────────────────────────────────────────────────────

  async clickNextPage(): Promise<void> {
    await this.click(L.paginationNext);
    await this.page.waitForTimeout(500);
  }

  async clickPrevPage(): Promise<void> {
    await this.click(L.paginationPrev);
    await this.page.waitForTimeout(500);
  }

  async getPaginationInfo(): Promise<string> {
    return this.getText(L.paginationInfo);
  }

  async setPageLength(value: string): Promise<void> {
    await this.selectOption(L.pageLengthSelect, value);
    await this.page.waitForTimeout(500);
  }

  async isNextPageEnabled(): Promise<boolean> {
    const btn = this.page.locator(L.paginationNext);
    const cls = await btn.getAttribute('class') ?? '';
    return !cls.includes('disabled');
  }

  // ─── Tray Scan Modal ───────────────────────────────────────────────────────

  async openTrayScanModal(batchId: string): Promise<void> {
    this.log.step(`Open tray scan modal for batch ${batchId}`);
    await this.page.locator(`.tray-scan-btn[data-batch-id="${batchId}"]`).click();
    await expect(this.page.locator(L.trayScanModal)).toBeVisible({ timeout: 10_000 });
  }

  async closeTrayScanModal(): Promise<void> {
    await this.click(L.closeTrayScanModal);
    await expect(this.page.locator(L.trayScanModal)).toBeHidden({ timeout: 5_000 });
  }

  async getModalPlatingStk(): Promise<string> {
    return this.getText(L.modalPlatingStk);
  }

  async getModalTrayQty(): Promise<string> {
    return this.getText(L.modalTrayQty);
  }

  async fillTrayId(trayId: string, inputIndex = 0): Promise<void> {
    this.log.step(`Fill tray ID: ${trayId}`);
    const inputs = this.page.locator(L.trayIdInput);
    await inputs.nth(inputIndex).fill(trayId);
    await inputs.nth(inputIndex).press('Enter');
  }

  async clickDraftTray(): Promise<void> {
    const { status } = await waitForApiResponse(
      this.page,
      '/dayplanning/draft_tray/',
      async () => { await this.click(L.trayScanDraftBtn); }
    );
    this.log.debug(`Draft tray API → ${status}`);
  }

  async clickSubmitTray(): Promise<void> {
    await this.click(L.trayScanSubmitBtn);
  }

  async clickCancelTray(): Promise<void> {
    await this.click(L.trayScanCancelBtn);
  }

  async getTrayScanError(): Promise<string> {
    return this.getText(L.trayQtyErrorFooter);
  }

  async assertTraySubmitSuccess(): Promise<void> {
    await this.assertElementVisible(L.alertSuccess);
    this.log.pass('Tray submission succeeded');
  }

  // ─── Day Planning View Modal ────────────────────────────────────────────────

  async openDayPlanningViewModal(batchId: string): Promise<void> {
    this.log.step(`Open DP view modal for batch ${batchId}`);
    await this.page.locator(`[data-batch-id="${batchId}"]`).first().click();
    await expect(this.page.locator(L.trayScanModalDayPlanning)).toBeVisible({ timeout: 10_000 });
  }

  async closeDayPlanningViewModal(): Promise<void> {
    await this.click(L.closeTrayScanModalDayPlanning);
  }

  // ─── Delete Batch ──────────────────────────────────────────────────────────

  async deleteBatch(batchId: string): Promise<void> {
    this.log.step(`Delete batch ${batchId}`);
    const { status } = await waitForApiResponse(
      this.page,
      '/dayplanning/delete_batch/',
      async () => {
        await this.page.locator(`.delete-batch-btn[data-batch-id="${batchId}"]`).click();
        // Confirm SweetAlert
        await this.page.locator(L.swalConfirmBtn).click();
      }
    );
    this.log.debug(`Delete batch API → ${status}`);
  }

  async cancelDeleteBatch(): Promise<void> {
    await this.click(L.swalCancelBtn);
  }

  // ─── Edit Quantity ─────────────────────────────────────────────────────────

  async openEditQtyModal(batchId: string): Promise<void> {
    this.log.step(`Open edit qty modal for batch ${batchId}`);
    await this.page.locator(`.edit-qty-btn[data-batch-id="${batchId}"]`).click();
  }

  // ─── Hold / Unhold ─────────────────────────────────────────────────────────

  async submitHoldRemark(remark: string): Promise<void> {
    this.log.step(`Submit hold remark: "${remark}"`);
    await expect(this.page.locator(L.holdRemarkModal)).toBeVisible({ timeout: 5_000 });
    await this.fill(L.holdRemarkInput, remark);
    await this.click(L.saveHoldRemarkBtn);
  }

  async closeHoldRemarkModal(): Promise<void> {
    await this.click(L.closeHoldRemarkModal);
  }

  async getHoldRemarkError(): Promise<string> {
    return this.getText(L.holdRemarkError);
  }

  // ─── Quick Help ────────────────────────────────────────────────────────────

  async closeQuickHelpPanel(): Promise<void> {
    if (await this.isVisible(L.quickHelpPanel)) {
      await this.click(L.quickHelpCloseBtn);
    }
  }
}
