// config/global-setup.ts
import { chromium, FullConfig } from '@playwright/test';
import dotenv from 'dotenv';
import path from 'path';
import fs from 'fs';
import { Logger } from '../utils/logger';

const log = Logger.getInstance('GlobalSetup');

async function globalSetup(config: FullConfig): Promise<void> {
  const env = process.env.TEST_ENV || 'dev';
  dotenv.config({ path: path.resolve(__dirname, `.env.${env}`) });

  log.info(`=== Global Setup START | ENV: ${env.toUpperCase()} ===`);

  // Create output directories
  const dirs = [
    'reports/html',
    'reports/json',
    'reports/junit',
    'reports/allure-results',
    'screenshots',
    'traces',
    'test-results',
    'fixtures/auth',
  ];
  for (const dir of dirs) {
    fs.mkdirSync(path.resolve(__dirname, '..', dir), { recursive: true });
  }

  // Authenticate and save state for each environment persona
  const browser = await chromium.launch({ headless: true });

  const personas = [
    {
      username: process.env.ADMIN_USERNAME ?? 'admin',
      password: process.env.ADMIN_PASSWORD ?? 'admin@123',
      stateFile: 'fixtures/auth/dev-state.json',
    },
  ];

  const baseURL = process.env.BASE_URL ?? 'http://localhost:8000';

  for (const persona of personas) {
    try {
      const context = await browser.newContext();
      const page = await context.newPage();

      await page.goto(`${baseURL}/accounts/login/`);
      await page.fill('#id_username', persona.username);
      await page.fill('#id_password', persona.password);
      await page.click('[type="submit"]');
      await page.waitForURL(`${baseURL}/home/`, { timeout: 15_000 });

      await context.storageState({
        path: path.resolve(__dirname, '..', persona.stateFile),
      });
      await context.close();
      log.info(`Auth state saved → ${persona.stateFile}`);
    } catch (err) {
      log.warn(`Auth setup failed for ${persona.username}: ${(err as Error).message}`);
      // Create empty state file so tests can still run (will fail gracefully)
      const emptyState = { cookies: [], origins: [] };
      fs.writeFileSync(
        path.resolve(__dirname, '..', persona.stateFile),
        JSON.stringify(emptyState)
      );
    }
  }

  await browser.close();
  log.info('=== Global Setup COMPLETE ===');
}

export default globalSetup;
