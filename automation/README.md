# TTT Day Planning — Playwright Automation Framework

**Enterprise-Grade Test Automation | Senior QA Architect Design**

---

## Framework Architecture

```
automation/
├── tests/                         # Test suites (organised by feature)
│   └── day-planning/
│       ├── dp-01-navigation.spec.ts
│       ├── dp-02-login.spec.ts
│       ├── dp-03-pick-table.spec.ts
│       ├── dp-04-tray-scan.spec.ts
│       ├── dp-05-bulk-upload.spec.ts
│       ├── dp-06-validation.spec.ts
│       ├── dp-07-negative-boundary.spec.ts
│       ├── dp-08-completed-table.spec.ts
│       └── dp-09-api-suite.spec.ts
├── pages/                         # Page Object Model
│   ├── base.page.ts
│   ├── login.page.ts
│   ├── day-planning-pick-table.page.ts
│   ├── day-planning-bulk-upload.page.ts
│   └── day-planning-completed-table.page.ts
├── locators/                      # Centralised locators
│   ├── login.locators.ts
│   └── day-planning.locators.ts
├── fixtures/                      # Custom test fixtures
│   ├── base.fixtures.ts
│   ├── auth.setup.ts
│   └── auth/                      # Saved auth states (gitignored)
├── utils/                         # Reusable utilities
│   ├── logger.ts
│   ├── helpers.ts
│   └── api-client.ts
├── test-data/                     # Test data JSON files
│   ├── users.json
│   └── day-planning.json
├── config/                        # Environment configuration
│   ├── environments.ts
│   ├── global-setup.ts
│   ├── global-teardown.ts
│   ├── .env.dev
│   ├── .env.qa
│   └── .env.uat
├── ci/                            # CI/CD pipelines
│   ├── github-actions.yml
│   ├── azure-pipelines.yml
│   └── Jenkinsfile
├── reports/                       # Generated reports (gitignored)
├── screenshots/                   # Failure screenshots (gitignored)
├── traces/                        # Playwright traces (gitignored)
├── playwright.config.ts
├── package.json
├── tsconfig.json
└── README.md
```

---

## Prerequisites

- Node.js v20+
- npm v10+

---

## Quick Start

```bash
# 1. Navigate to automation folder
cd automation

# 2. Install dependencies
npm install

# 3. Install Playwright browsers
npx playwright install --with-deps

# 4. Configure environment
cp config/.env.dev config/.env.local
# Edit config/.env.local with your credentials

# 5. Run smoke tests
npm run test:smoke

# 6. Open HTML report
npm run test:report
```

---

## Execution Commands

| Command | Description |
|---------|-------------|
| `npm test` | Run all tests headless |
| `npm run test:headed` | Run all tests headed (visible browser) |
| `npm run test:debug` | Run with Playwright inspector |
| `npm run test:ui` | Open Playwright UI mode |
| `npm run test:smoke` | Run `@smoke` tagged tests only |
| `npm run test:sanity` | Run `@sanity` tagged tests only |
| `npm run test:regression` | Run `@regression` tagged tests only |
| `npm run test:dayplanning` | Run all Day Planning tests |
| `npm run test:dev` | Run on DEV environment (Chromium) |
| `npm run test:qa` | Run on QA environment (Chromium) |
| `npm run test:uat` | Run on UAT environment (Chromium) |
| `npm run test:parallel` | Run with 4 parallel workers |
| `npm run test:report` | Open last HTML report |
| `npm run clean` | Clean all generated artifacts |

### Environment-specific execution

```bash
# Target a specific environment
TEST_ENV=qa npm test

# Run headless explicitly
HEADLESS=true npm test

# Run headed
HEADLESS=false npm test

# Run with slow motion (500ms delay)
SLOW_MO=500 npm test
```

### Specific test file execution

```bash
# Single spec
npx playwright test tests/day-planning/dp-01-navigation.spec.ts

# Specific test by name grep
npx playwright test --grep "TC-DP-06"

# Multiple greps
npx playwright test --grep "@smoke|@sanity"
```

---

## Environment Strategy

| Environment | Base URL | Purpose |
|-------------|----------|---------|
| `dev` | `http://localhost:8000` | Local developer testing |
| `qa` | `http://qa.ttt-internal.local:8000` | QA team testing |
| `uat` | `http://uat.ttt-internal.local:8000` | UAT / pre-production |

Credentials are loaded from `config/.env.<ENV>` and can be overridden by environment variables.

---

## Test Tag Strategy

| Tag | Purpose | When to Run |
|-----|---------|-------------|
| `@smoke` | Core happy-path checks | Every commit/push |
| `@sanity` | Critical workflow validations | Every deployment |
| `@regression` | Full coverage suite | Nightly / release |

---

## Day Planning Coverage Matrix

| Area | Test IDs | Count |
|------|----------|-------|
| Navigation | TC-DP-01 to TC-DP-05 | 5 |
| Login Validation | TC-DP-06 to TC-DP-18 | 13 |
| Pick Table | TC-DP-19 to TC-DP-35 | 17 |
| Tray Scan Modal | TC-DP-36 to TC-DP-52 | 17 |
| Bulk Upload | TC-DP-53 to TC-DP-68 | 16 |
| Field Validation | TC-DP-69 to TC-DP-82 | 14 |
| Negative & Boundary | TC-DP-83 to TC-DP-100 | 18 |
| Completed Table | TC-DP-101 to TC-DP-110 | 10 |
| API Suite | TC-DP-111 + parametric | 15+ |
| **TOTAL** | | **125+** |

---

## Reporting

Reports are generated in:

- `reports/html/index.html` — Playwright HTML report (interactive)
- `reports/json/results.json` — JSON for downstream processing
- `reports/junit/results.xml` — JUnit for CI integrations
- `reports/allure-results/` — Allure raw data
- `reports/logs/automation.log` — Structured execution log

---

## Failure Artifacts

On test failure:
- Screenshots → `screenshots/<test-name>_<timestamp>.png`
- Videos → `test-results/<test-name>/video.webm`
- Traces → `traces/<test-name>.zip` (open with `npx playwright show-trace`)

---

## Security Notes

- Credentials are **never hardcoded** in test files
- All auth state files are in `fixtures/auth/` (add to `.gitignore`)
- SQL injection and XSS tests are included to verify backend resilience
- No application source code was modified

---

## CI/CD

| Platform | File |
|----------|------|
| GitHub Actions | `ci/github-actions.yml` |
| Azure DevOps | `ci/azure-pipelines.yml` |
| Jenkins | `ci/Jenkinsfile` |

---

*Framework designed and implemented by TTT QA Automation Team.*
*Developer source code: UNMODIFIED. Automation: FULLY ISOLATED.*
