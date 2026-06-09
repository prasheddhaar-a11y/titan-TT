import { defineConfig, devices } from '@playwright/test';
import dotenv from 'dotenv';
import path from 'path';

// Load environment-specific .env
const ENV = process.env.TEST_ENV || 'dev';
dotenv.config({ path: path.resolve(__dirname, `config/.env.${ENV}`) });

const BASE_URL = process.env.BASE_URL || 'http://localhost:8000';

export default defineConfig({
  // ─── Test Directory ────────────────────────────────────────────────────────
  testDir: './tests',

  // ─── Global Timeout ────────────────────────────────────────────────────────
  timeout: 60_000,
  expect: { timeout: 10_000 },

  // ─── Retry Configuration ───────────────────────────────────────────────────
  retries: process.env.CI ? 2 : 1,

  // ─── Parallel Execution ────────────────────────────────────────────────────
  workers: process.env.CI ? 4 : 2,
  fullyParallel: false, // Day Planning has stateful workflows — keep suite-level parallelism

  // ─── Reporter ──────────────────────────────────────────────────────────────
  reporter: [
    ['list'],
    ['html', { outputFolder: 'reports/html', open: 'never' }],
    ['json', { outputFile: 'reports/json/results.json' }],
    ['junit', { outputFile: 'reports/junit/results.xml' }],
    ['allure-playwright', { outputFolder: 'reports/allure-results' }],
  ],

  // ─── Global Use ────────────────────────────────────────────────────────────
  use: {
    baseURL: BASE_URL,
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
    headless: process.env.HEADLESS !== 'false',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    locale: 'en-US',
    timezoneId: 'Asia/Kolkata',
  },

  // ─── Output Directories ────────────────────────────────────────────────────
  outputDir: 'test-results',

  // ─── Projects (Environments × Browsers) ───────────────────────────────────
  projects: [
    // ── DEV environment ──
    {
      name: 'chromium-dev',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.DEV_URL || 'http://localhost:8000',
        storageState: 'fixtures/auth/dev-state.json',
      },
      testMatch: '**/*.spec.ts',
    },

    // ── QA environment ──
    {
      name: 'chromium-qa',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.QA_URL || 'http://qa.ttt-internal.local:8000',
        storageState: 'fixtures/auth/qa-state.json',
      },
      testMatch: '**/*.spec.ts',
    },

    // ── UAT environment ──
    {
      name: 'chromium-uat',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: process.env.UAT_URL || 'http://uat.ttt-internal.local:8000',
        storageState: 'fixtures/auth/uat-state.json',
      },
      testMatch: '**/*.spec.ts',
    },

    // ── Firefox (cross-browser) ──
    {
      name: 'firefox',
      use: {
        ...devices['Desktop Firefox'],
        storageState: 'fixtures/auth/dev-state.json',
      },
      testMatch: '**/*.spec.ts',
    },

    // ── Setup project — runs auth once before tests ──
    {
      name: 'setup',
      testMatch: '**/auth.setup.ts',
      use: { headless: true },
    },
  ],

  // ─── Global Setup / Teardown ───────────────────────────────────────────────
  globalSetup: './config/global-setup.ts',
  globalTeardown: './config/global-teardown.ts',
});
