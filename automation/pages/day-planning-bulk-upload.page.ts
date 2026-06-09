// pages/day-planning-bulk-upload.page.ts
// Page Object for Day Planning Bulk Upload

import { Page, expect } from '@playwright/test';
import { BasePage } from './base.page';
import { DayPlanningBulkUploadLocators as L } from '../locators/day-planning.locators';
import path from 'path';

export class DayPlanningBulkUploadPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async goto(): Promise<void> {
    await this.navigate('/dayplanning/bulk_upload/');
  }

  async downloadTemplate(): Promise<string> {
    this.log.step('Download Excel template');
    const [download] = await Promise.all([
      this.page.waitForEvent('download'),
      this.click(L.downloadTemplateBtn),
    ]);
    const filePath = path.join('downloads', download.suggestedFilename());
    await download.saveAs(filePath);
    this.log.info(`Template downloaded → ${filePath}`);
    return filePath;
  }

  async uploadFile(filePath: string): Promise<void> {
    this.log.step(`Upload file: ${filePath}`);
    await this.page.locator(L.fileInput).setInputFiles(filePath);
  }

  async clickUpload(): Promise<void> {
    await this.click(L.uploadButton);
    await this.page.waitForLoadState('networkidle');
  }

  async uploadAndPreview(filePath: string): Promise<void> {
    await this.uploadFile(filePath);
    await this.clickUpload();
    await expect(this.page.locator(L.previewTable)).toBeVisible({ timeout: 15_000 });
  }

  async confirmUpload(): Promise<void> {
    await this.click(L.confirmUploadBtn);
    await this.page.waitForLoadState('networkidle');
  }

  async cancelUpload(): Promise<void> {
    await this.click(L.cancelUploadBtn);
  }

  async assertUploadError(errorText?: string): Promise<void> {
    await expect(this.page.locator(L.uploadError)).toBeVisible({ timeout: 10_000 });
    if (errorText) {
      await expect(this.page.locator(L.uploadError)).toContainText(errorText);
    }
  }

  async assertUploadSuccess(): Promise<void> {
    await expect(this.page.locator(L.uploadSuccess)).toBeVisible({ timeout: 15_000 });
    this.log.pass('Bulk upload succeeded');
  }

  async assertPreviewVisible(): Promise<void> {
    await expect(this.page.locator(L.previewTable)).toBeVisible({ timeout: 10_000 });
  }

  async assertPageLoaded(): Promise<void> {
    await expect(this.page.locator(L.fileInput)).toBeVisible({ timeout: 10_000 });
    this.log.pass('Bulk upload page loaded');
  }
}
