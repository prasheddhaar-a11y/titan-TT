// fixtures/auth.setup.ts
// Authentication setup — runs once before all tests to create storageState files

import { test as setup, expect } from '@playwright/test';
import path from 'path';
import dotenv from 'dotenv';

const ENV = process.env.TEST_ENV || 'dev';
dotenv.config({ path: path.resolve(__dirname, `../config/.env.${ENV}`) });

const authFile = path.resolve(__dirname, 'auth/dev-state.json');

setup('Authenticate as admin', async ({ page }) => {
  const baseUrl = process.env.BASE_URL ?? 'http://localhost:8000';
  const username = process.env.ADMIN_USERNAME ?? 'admin';
  const password = process.env.ADMIN_PASSWORD ?? 'admin@123';

  await page.goto(`${baseUrl}/accounts/login/`);
  await page.fill('#id_username', username);
  await page.fill('#id_password', password);
  await page.click('[type="submit"]');

  // Wait for successful login redirect
  await expect(page).toHaveURL(new RegExp('home'), { timeout: 20_000 });

  // Save auth state
  await page.context().storageState({ path: authFile });
  console.log(`[AUTH SETUP] State saved → ${authFile}`);
});
