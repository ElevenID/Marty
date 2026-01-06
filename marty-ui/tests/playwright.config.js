// @ts-check
const { defineConfig, devices } = require('@playwright/test');

const isCI = !!process.env.CI;
const timeouts = {
  test: isCI ? 120_000 : 30_000,      // Reduced from 90s to 30s for faster failures
  expect: isCI ? 10_000 : 5_000,      // Reduced from 8s to 5s
  action: isCI ? 30_000 : 10_000,     // Reduced from 20s to 10s
  navigation: isCI ? 30_000 : 10_000, // Reduced from 20s to 10s
  webServer: 120_000,
};

/**
 * Project-based test configuration for parallel execution:
 * - smoke: Fast, seeded-data tests (parallel)
 * - integration: Read-only API tests (parallel)
 * - workflows: Sequential dynamic-data tests
 * - vendor/applicant/push-notifications: Domain-specific tests
 */

/**
 * @see https://playwright.dev/docs/test-configuration
 */
module.exports = defineConfig({
  testDir: './e2e',
  timeout: timeouts.test,
  expect: {
    timeout: timeouts.expect,
  },
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: isCI,
  /* Retry on CI only */
  retries: isCI ? 2 : 0,
  /* Reporter to use. See https://playwright.dev/docs/test-reporters */
  reporter: [
    ['html'],
    ['json', { outputFile: 'test-results.json' }],
    ['junit', { outputFile: 'test-results.xml' }]
  ],
  /* Shared settings for all the projects below. */
  use: {
    /* Base URL to use in actions like `await page.goto('/')`. */
    baseURL: process.env.BASE_URL || 'http://localhost:9080',
    /* Collect trace when retrying the failed test. */
    trace: 'on-first-retry',
    /* Take screenshot on failure */
    screenshot: 'only-on-failure',
    /* Record video on failure */
    video: 'retain-on-failure',
    /* Global timeout for each action */
    actionTimeout: timeouts.action,
    /* Global timeout for navigation */
    navigationTimeout: timeouts.navigation
  },

  /* Configure projects for organized test execution */
  projects: [
    // Smoke tests - fast, seeded-data, parallel-safe
    {
      name: 'smoke',
      testMatch: '**/smoke/**/*.spec.js',
      fullyParallel: true,
      workers: isCI ? 4 : undefined,
      use: { ...devices['Desktop Chrome'] },
    },
    // Integration tests - read-only API tests, parallel-safe
    {
      name: 'integration',
      testMatch: '**/integration/**/*.spec.js',
      fullyParallel: true,
      workers: isCI ? 2 : undefined,
      use: { ...devices['Desktop Chrome'] },
    },
    // Workflow tests - sequential, dynamic data
    {
      name: 'workflows',
      testMatch: '**/workflows/**/*.spec.js',
      fullyParallel: false,
      workers: 1,
      use: { ...devices['Desktop Chrome'] },
    },
    // Vendor tests
    {
      name: 'vendor',
      testMatch: '**/vendor/**/*.spec.js',
      fullyParallel: false,
      workers: 1,
      use: { ...devices['Desktop Chrome'] },
    },
    // Applicant tests
    {
      name: 'applicant',
      testMatch: '**/applicant/**/*.spec.js',
      fullyParallel: false,
      workers: 1,
      use: { ...devices['Desktop Chrome'] },
    },
    // Push notification tests
    {
      name: 'push-notifications',
      testMatch: '**/push-notifications/**/*.spec.js',
      fullyParallel: false,
      workers: 1,
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  /* Global setup and teardown */
  globalSetup: require.resolve('./utils/global-setup.js'),
  globalTeardown: require.resolve('./utils/global-teardown.js'),

  /* Run your local dev server before starting the tests */
  // Skip webServer check when running in Docker (CI=true)
  ...(isCI ? {} : {
    webServer: {
      command: 'echo "Demo should be running"',
      url: process.env.BASE_URL || 'http://localhost:9080',
      reuseExistingServer: true,
      timeout: timeouts.webServer,
    },
  }),
});
