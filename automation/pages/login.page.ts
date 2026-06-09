// pages/login.page.ts
// Page Object for the TTT Login page

import { Page, expect } from '@playwright/test';
import { BasePage } from './base.page';
import { LoginLocators } from '../locators/login.locators';

export class LoginPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  // ─── Navigation ────────────────────────────────────────────────────────────

  async goto(): Promise<void> {
    await this.navigate('/accounts/login/');
  }

  // ─── Actions ───────────────────────────────────────────────────────────────

  async enterUsername(username: string): Promise<void> {
    await this.fill(LoginLocators.usernameInput, username);
  }

  async enterPassword(password: string): Promise<void> {
    await this.fill(LoginLocators.passwordInput, password);
  }

  async clickLogin(): Promise<void> {
    await this.click(LoginLocators.submitButton);
  }

  async loginAs(username: string, password: string): Promise<void> {
    this.log.step(`Login as ${username}`);
    await this.enterUsername(username);
    await this.enterPassword(password);
    await this.clickLogin();
  }

  async loginAndWaitForHome(username: string, password: string): Promise<void> {
    await this.loginAs(username, password);
    await this.page.waitForURL(/home/, { timeout: 20_000 });
    this.log.pass(`Logged in as ${username}`);
  }

  // ─── Assertions ────────────────────────────────────────────────────────────

  async assertLoginPageVisible(): Promise<void> {
    await expect(this.page.locator(LoginLocators.loginForm)).toBeVisible();
    await this.assertUrlContains('login');
  }

  async assertLoginError(): Promise<void> {
    await expect(this.page.locator(LoginLocators.errorMessage)).toBeVisible({ timeout: 5_000 });
  }

  async assertStillOnLoginPage(): Promise<void> {
    await this.assertUrlContains('login');
  }

  async getErrorMessage(): Promise<string> {
    return this.getText(LoginLocators.errorMessage);
  }

  async isLoggedIn(): Promise<boolean> {
    return !this.page.url().includes('login');
  }
}
