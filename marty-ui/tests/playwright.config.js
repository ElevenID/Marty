// @ts-check
const { defineConfig, devices } = require('@playwright/test');

const isCI = !!process.env.CI;
const isFast = process.env.PW_FAST === '1' || process.env.PW_FAST === 'true';
const timeouts = {
  test: isFast ? 60_000 : isCI ? 120_000 : 90_000,
  expect: isFast ? 5_000 : isCI ? 10_000 : 8_000,
  action: isFast ? 10_000 : isCI ? 30_000 : 20_000,
  navigation: isFast ? 15_000 : isCI ? 30_000 : 20_000,
  webServer: isFast ? 60_000 : 120_000,
};
const chromiumProject = {
  name: 'chromium',
  use: { ...devices['Desktop Chrome'] },
};
const projects = isFast ? [
  chromiumProject,
] : [
  chromiumProject,
  {
    name: 'firefox',
    use: { ...devices['Desktop Firefox'] },
  },
  {
    name: 'webkit',
    use: { ...devices['Desktop Safari'] },
  },
  /* Test against mobile viewports. */
  {
    name: 'Mobile Chrome',
    use: { ...devices['Pixel 5'] },
  },
  {
    name: 'Mobile Safari',
    use: { ...devices['iPhone 12'] },
  },
];

/**
 * @see https://playwright.dev/docs/test-configuration
 */
module.exports = defineConfig({
  testDir: './e2e',
  /* Run tests in files in parallel */
  fullyParallel: true,
  timeout: timeouts.test,
  expect: {
    timeout: timeouts.expect,
  },
  grepInvert: isFast ? /@slow/ : undefined,
  maxFailures: isFast ? 1 : undefined,
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: isCI,
  /* Retry on CI only */
  retries: isCI ? 2 : 0,
  /* Opt out of parallel tests on CI. */
  workers: isCI ? 1 : undefined,
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

  /* Configure projects for major browsers */
  projects,

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
