// pages/base.page.ts
// Base Page Object — all page objects extend this class

import { Page, expect } from '@playwright/test';
import { Logger } from '../utils/logger';
import { waitForLoader, takeScreenshot } from '../utils/helpers';
import { CommonLocators } from '../locators/day-planning.locators';

export abstract class BasePage {
  protected readonly log: Logger;

  constructor(protected readonly page: Page) {
    this.log = Logger.getInstance(this.constructor.name);
  }

  // ─── Navigation ────────────────────────────────────────────────────────────

  async navigate(path: string): Promise<void> {
    this.log.step(`Navigate to ${path}`);
    await this.page.goto(path);
    await this.waitForPageLoad();
  }

  async waitForPageLoad(): Promise<void> {
    await this.page.waitForLoadState('domcontentloaded');
    await waitForLoader(this.page);
  }

  async getPageTitle(): Promise<string> {
    return this.page.title();
  }

  async getCurrentUrl(): Promise<string> {
    return this.page.url();
  }

  // ─── Assertions ────────────────────────────────────────────────────────────

  async assertUrlContains(fragment: string): Promise<void> {
    await expect(this.page).toHaveURL(new RegExp(fragment));
  }

  async assertElementVisible(selector: string, timeout = 10_000): Promise<void> {
    await expect(this.page.locator(selector).first()).toBeVisible({ timeout });
  }

  async assertElementHidden(selector: string): Promise<void> {
    await expect(this.page.locator(selector).first()).toBeHidden();
  }

  async assertText(selector: string, text: string): Promise<void> {
    await expect(this.page.locator(selector).first()).toContainText(text);
  }

  // ─── Common Actions ────────────────────────────────────────────────────────

  async click(selector: string): Promise<void> {
    this.log.debug(`Click → ${selector}`);
    await this.page.locator(selector).first().click();
  }

  async fill(selector: string, value: string): Promise<void> {
    this.log.debug(`Fill [${selector}] = "${value}"`);
    const field = this.page.locator(selector).first();
    await field.clear();
    await field.fill(value);
  }

  async selectOption(selector: string, value: string): Promise<void> {
    await this.page.locator(selector).first().selectOption(value);
  }

  async getText(selector: string): Promise<string> {
    return (await this.page.locator(selector).first().textContent()) ?? '';
  }

  async isVisible(selector: string): Promise<boolean> {
    return this.page.locator(selector).first().isVisible();
  }

  async screenshot(name: string): Promise<void> {
    await takeScreenshot(this.page, name);
  }

  // ─── Navbar ────────────────────────────────────────────────────────────────

  async logout(): Promise<void> {
    this.log.step('Logout');
    await this.click(CommonLocators.logoutLink);
    await this.page.waitForURL(/login/);
  }
}
