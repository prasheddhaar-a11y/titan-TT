// utils/helpers.ts
// Generic reusable helpers for the automation framework

import { Page, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { Logger } from './logger';

const log = Logger.getInstance('Helpers');

// ─── Wait Helpers ─────────────────────────────────────────────────────────────

/**
 * Waits for a network request matching a URL pattern and returns its response.
 */
export async function waitForApiResponse(
  page: Page,
  urlPattern: string | RegExp,
  action: () => Promise<void>
): Promise<{ status: number; body: unknown }> {
  const [response] = await Promise.all([
    page.waitForResponse((res) =>
      typeof urlPattern === 'string'
        ? res.url().includes(urlPattern)
        : urlPattern.test(res.url())
    ),
    action(),
  ]);
  const status = response.status();
  let body: unknown = null;
  try { body = await response.json(); } catch { /* not JSON */ }
  return { status, body };
}

/**
 * Waits until the page loader/spinner disappears.
 */
export async function waitForLoader(page: Page, timeout = 15_000): Promise<void> {
  const loaderSelectors = ['.loading', '.spinner', '#loader', '[data-loading]'];
  for (const sel of loaderSelectors) {
    const el = page.locator(sel).first();
    if (await el.isVisible({ timeout: 1_000 }).catch(() => false)) {
      await el.waitFor({ state: 'hidden', timeout });
    }
  }
}

// ─── Screenshot Helpers ───────────────────────────────────────────────────────

/**
 * Takes a timestamped screenshot to the screenshots directory.
 */
export async function takeScreenshot(page: Page, name: string): Promise<string> {
  const dir = path.resolve(__dirname, '..', 'screenshots');
  fs.mkdirSync(dir, { recursive: true });
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const filePath = path.join(dir, `${name}_${timestamp}.png`);
  await page.screenshot({ path: filePath, fullPage: true });
  log.info(`Screenshot saved → ${filePath}`);
  return filePath;
}

// ─── Assertion Helpers ────────────────────────────────────────────────────────

/**
 * Asserts a toast/alert message is visible and contains the expected text.
 */
export async function assertToast(
  page: Page,
  expectedText: string,
  timeout = 10_000
): Promise<void> {
  const toastSelectors = [
    '.toast',
    '.alert',
    '.swal2-popup',
    '[role="alert"]',
    '.notification',
  ];
  let found = false;
  for (const sel of toastSelectors) {
    const el = page.locator(sel).filter({ hasText: expectedText }).first();
    if (await el.isVisible({ timeout }).catch(() => false)) {
      await expect(el).toContainText(expectedText);
      found = true;
      break;
    }
  }
  if (!found) {
    throw new Error(`Toast with text "${expectedText}" not found after ${timeout}ms`);
  }
}

// ─── Form Helpers ─────────────────────────────────────────────────────────────

/**
 * Fills a form field after clearing its existing value.
 */
export async function fillField(page: Page, selector: string, value: string): Promise<void> {
  const field = page.locator(selector);
  await field.clear();
  await field.fill(value);
  log.debug(`Filled [${selector}] with "${value}"`);
}

// ─── Table Helpers ────────────────────────────────────────────────────────────

/**
 * Returns the count of rows in a table body (excluding header).
 */
export async function getTableRowCount(page: Page, tableSelector: string): Promise<number> {
  const rows = page.locator(`${tableSelector} tbody tr`);
  return rows.count();
}

/**
 * Gets all cell texts from a specific column index (0-based) in a table.
 */
export async function getColumnValues(
  page: Page,
  tableSelector: string,
  colIndex: number
): Promise<string[]> {
  const cells = page.locator(`${tableSelector} tbody tr td:nth-child(${colIndex + 1})`);
  const count = await cells.count();
  const values: string[] = [];
  for (let i = 0; i < count; i++) {
    values.push((await cells.nth(i).textContent()) ?? '');
  }
  return values;
}

// ─── Data Helpers ─────────────────────────────────────────────────────────────

/**
 * Generates a timestamp-based unique identifier for test data.
 */
export function generateUniqueId(prefix = 'TEST'): string {
  return `${prefix}_${Date.now()}`;
}

/**
 * Reads a JSON test-data file from the test-data directory.
 */
export function loadTestData<T>(fileName: string): T {
  const filePath = path.resolve(__dirname, '..', 'test-data', fileName);
  const raw = fs.readFileSync(filePath, 'utf-8');
  return JSON.parse(raw) as T;
}

// ─── Retry Helper ─────────────────────────────────────────────────────────────

/**
 * Retries an async function up to `maxAttempts` times with a delay.
 */
export async function retryAction<T>(
  fn: () => Promise<T>,
  maxAttempts = 3,
  delayMs = 1_000
): Promise<T> {
  let lastErr: Error | undefined;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastErr = err as Error;
      log.warn(`Attempt ${attempt}/${maxAttempts} failed: ${lastErr.message}`);
      if (attempt < maxAttempts) await new Promise((r) => setTimeout(r, delayMs));
    }
  }
  throw lastErr;
}
