/**
 * Credential Issuance E2E Tests
 *
 * Validates the core issuance flow using current UI routes/testids:
 * 1. Applicant enables push notifications
 * 2. Applicant submits mDL application
 * 3. Admin approves application and issues document
 * 4. Notification is queued and applicant sees issued document
 */

const { test, expect } = require('@playwright/test');
const path = require('path');
const {
  AuthHelpers,
  PushNotificationHelpers,
  getVendorOrganizationId,
} = require('../utils/test-helpers');

const inputSelectorFor = (testId) =>
  `[data-testid="${testId}"] input:not([aria-hidden="true"]), ` +
  `[data-testid="${testId}"] textarea:not([aria-hidden="true"])`;

const fillByTestId = async (page, testId, value) => {
  await page.locator(inputSelectorFor(testId)).fill(value);
};

const inputValueByTestId = async (page, testId) =>
  page.locator(inputSelectorFor(testId)).inputValue();

const selectMuiOption = async (page, testId, value) => {
  const trigger = page.locator(
    `[data-testid="${testId}"] [role="combobox"], ` +
    `[data-testid="${testId}"] [role="button"]`
  );
  if (await trigger.count()) {
    await trigger.first().click();
  } else {
    await page.click(`[data-testid="${testId}"]`);
  }
  await page.locator(`ul[role="listbox"] li[data-value="${value}"]`).click();
};

const registerPushToken = async (page) => {
  let userId = null;
  let orgId = null;
  const meResponse = await page.request.get('/auth/me');
  if (meResponse.ok()) {
    const meData = await meResponse.json();
    userId = meData?.user?.user_id || null;
    orgId = meData?.user?.organization_id || null;
  }

  const deviceIdBase = `web-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const deviceId = orgId ? `${orgId}:${deviceIdBase}` : deviceIdBase;

  const registerResponse = await page.request.post('/api/devices/register', {
    headers: userId ? { 'X-User-ID': userId } : {},
    data: {
      device_id: deviceId,
      fcm_token: `fcm_web_${Date.now()}`,
      platform: 'web',
      app_version: 'web-1.0.0',
    },
  });
  expect(registerResponse.ok()).toBeTruthy();
};

const PORTRAIT_PATH = path.resolve(__dirname, '../fixtures/test-portrait.jpg');

const MDL_APPLICATION_DATA = {
  firstName: 'Maria',
  lastName: 'Credentialist',
  email: 'maria.credential@example.com',
  dateOfBirth: '1988-07-20',
  address: {
    street: '456 Oak Avenue',
    city: 'Austin',
    state: 'TX',
    zip: '78701',
  },
  licenseClass: 'C',
};

test.use({ permissions: ['notifications'] });

test.describe.serial('Credential Issuance Flow', () => {
  let auth;
  let pushHelpers;
  let applicationId;
  let issuedDocumentNumber;
  let credentialConfigId;
  let organizationId;
  let applicantUserId;

  test.beforeAll(async ({ browser }) => {
    const vendorOrg = await getVendorOrganizationId(browser);
    organizationId = vendorOrg.organizationId;

    const page = await browser.newPage();
    const adminAuth = new AuthHelpers(page);
    await page.goto('/');
    await adminAuth.loginAsSeededUser('admin');

    const listResponse = await page.request.get(
      `/api/organizations/${organizationId}/credential-types`
    );
    if (!listResponse.ok()) {
      throw new Error('Failed to list credential configurations');
    }
    const listData = await listResponse.json();
    const configs = listData.credential_types || [];
    const existing = configs.find((config) => config.credential_type === 'drivers_license');

    if (existing) {
      credentialConfigId = existing.id;
    } else {
      const createResponse = await page.request.post(
        `/api/organizations/${organizationId}/credential-types`,
        {
          data: {
            credential_type: 'drivers_license',
            display_name: 'Mobile Driver\'s License',
            validity_days: 365,
          },
        }
      );
      if (!createResponse.ok()) {
        throw new Error('Failed to create credential configuration');
      }
      const created = await createResponse.json();
      credentialConfigId = created.credential_type?.id;
    }

    await page.close();
  });

  test.beforeEach(async ({ page }) => {
    auth = new AuthHelpers(page);
    pushHelpers = new PushNotificationHelpers(page);
  });

  test('applicant enables push notifications', async ({ page }) => {
    await page.goto('/');
    await auth.loginAsSeededUser('applicant1');
    const meResponse = await page.request.get('/auth/me');
    if (meResponse.ok()) {
      const meData = await meResponse.json();
      applicantUserId = meData?.user?.user_id || null;
      pushHelpers.setUserId(applicantUserId);
    }

    await page.goto('/settings/notifications');
    await expect(page.locator('[data-testid="notification-preferences-page"]')).toBeVisible({
      timeout: 10000,
    });

    const pushToggle = page.locator('[data-testid="push-master-toggle"] input');
    if (await pushToggle.isDisabled()) {
      await registerPushToken(page);
      return;
    }

    if (!(await pushToggle.isChecked())) {
      const registerResponse = page.waitForResponse(
        (response) =>
          response.url().includes('/api/devices/register') && response.ok()
      );
      await page.click('[data-testid="push-master-toggle"]');
      await registerResponse;

      await expect(page.locator('[data-testid="notification-snackbar"]')).toBeVisible({
        timeout: 10000,
      });
    } else {
      await expect(pushToggle).toBeChecked();
    }
  });

  test('applicant submits mDL application', async ({ page }) => {
    await page.goto('/');
    await auth.loginAsSeededUser('applicant1');
    await page.goto(`/apply/${credentialConfigId}`);

    await expect(page.locator('[data-testid="credential-application-form"]')).toBeVisible({
      timeout: 10000,
    });

    await fillByTestId(page, 'first-name-input', MDL_APPLICATION_DATA.firstName);
    await fillByTestId(page, 'last-name-input', MDL_APPLICATION_DATA.lastName);
    await fillByTestId(page, 'dob-input', MDL_APPLICATION_DATA.dateOfBirth);
    if ((await inputValueByTestId(page, 'email-input')) === '') {
      await fillByTestId(page, 'email-input', MDL_APPLICATION_DATA.email);
    }
    await page.click('[data-testid="next-step-btn"]');

    await expect(page.locator('[data-testid="address-step"]')).toBeVisible();
    await fillByTestId(page, 'street-input', MDL_APPLICATION_DATA.address.street);
    await fillByTestId(page, 'city-input', MDL_APPLICATION_DATA.address.city);
    await selectMuiOption(page, 'state-select', MDL_APPLICATION_DATA.address.state);
    await fillByTestId(page, 'zip-input', MDL_APPLICATION_DATA.address.zip);
    await page.click('[data-testid="next-step-btn"]');

    await expect(page.locator('[data-testid="license-step"]')).toBeVisible();
    await selectMuiOption(page, 'license-class-select', MDL_APPLICATION_DATA.licenseClass);
    const docNumber = `DL${Date.now().toString().slice(-8)}`;
    await fillByTestId(page, 'document-number-input', docNumber);
    await page.click('[data-testid="next-step-btn"]');

    await expect(page.locator('[data-testid="photo-step"]')).toBeVisible();
    await page.locator('[data-testid="portrait-upload-input"]').setInputFiles(PORTRAIT_PATH);
    await expect(page.locator('[data-testid="photo-preview"]')).toBeVisible();
    await page.click('[data-testid="next-step-btn"]');

    await expect(page.locator('[data-testid="review-step"]')).toBeVisible();
    await page.check('[data-testid="accept-terms-checkbox"]');
    await page.click('[data-testid="submit-application-btn"]');

    await expect(page.locator('[data-testid="application-submitted"]')).toBeVisible({
      timeout: 15000,
    });
    applicationId = await page.getAttribute('[data-testid="application-id"]', 'data-value');
    expect(applicationId).toBeTruthy();
  });

  test('admin approves application', async ({ page }) => {
    await page.goto('/');
    await auth.loginAsSeededUser('admin');

    expect(applicationId).toBeTruthy();
    await page.goto('/applicants');

    const row = page.locator(`[data-testid="application-row-${applicationId}"]`);
    await expect(row).toBeVisible({ timeout: 10000 });
    await row.locator('[data-testid="view-application-btn"]').click();

    await expect(page.locator('[data-testid="application-detail-view"]')).toBeVisible({
      timeout: 10000,
    });

    let pendingChecks = page.locator('[data-testid^="check-pass-btn-"]');
    while (await pendingChecks.count()) {
      await pendingChecks.first().click();
      await page.waitForTimeout(300);
      pendingChecks = page.locator('[data-testid^="check-pass-btn-"]');
    }

    await page.locator('[data-testid="application-detail-view"] button:has-text("Close")').click();

    await expect(row.locator('[data-testid="approve-application-btn"]')).toBeVisible({
      timeout: 10000,
    });
    await row.locator('[data-testid="approve-application-btn"]').click();

    await expect(page.locator('[data-testid="approval-dialog"]')).toBeVisible({ timeout: 10000 });
    await fillByTestId(page, 'approval-notes', 'Documents verified. All requirements met.');
    await page.click('[data-testid="confirm-approval-btn"]');
    await expect(page.locator('[data-testid="approval-dialog"]')).toBeHidden({ timeout: 10000 });
  });

  test('admin issues credential', async ({ page }) => {
    await page.goto('/');
    await auth.loginAsSeededUser('admin');
    if (applicantUserId) {
      pushHelpers.setUserId(applicantUserId);
      await pushHelpers.clearAllNotifications();
    }

    expect(applicationId).toBeTruthy();
    await page.goto('/documents');
    await page.click('[data-testid="issue-document-button"]');

    await expect(page.locator('[data-testid="issue-document-dialog"]')).toBeVisible({
      timeout: 10000,
    });
    await page.click('[data-testid="issue-tab-applicant"]');

    await selectMuiOption(page, 'approved-applicant-select', applicationId);

    issuedDocumentNumber = `DL${Date.now().toString().slice(-8)}`;
    await fillByTestId(page, 'issue-document-number', issuedDocumentNumber);

    await page.click('[data-testid="confirm-issue-document"]');

    await expect(page.locator('[data-testid="documents-success-snackbar"]')).toBeVisible({
      timeout: 30000,
    });
    await expect(page.locator('[data-testid="issue-document-dialog"]')).toBeHidden({
      timeout: 10000,
    });
  });

  test('applicant receives notification and sees document', async ({ page }) => {
    expect(applicationId).toBeTruthy();
    expect(issuedDocumentNumber).toBeTruthy();
    if (applicantUserId) {
      pushHelpers.setUserId(applicantUserId);
    }

    await expect.poll(async () => {
      const notifications = await pushHelpers.getNotificationsByEventType('credential_offer');
      return notifications.find(
        (notification) =>
          notification.data?.application_id === applicationId || notification.data?.document_id
      );
    }, { timeout: 15000 }).toBeTruthy();

    await page.goto('/');
    await auth.loginAsSeededUser('applicant1');
    await page.goto('/my-documents');

    await expect(page.locator('[data-testid="my-documents-page"]')).toBeVisible({ timeout: 10000 });
    const issuedDocument = page.locator('[data-testid="document-number"]', {
      hasText: issuedDocumentNumber,
    });
    await expect(issuedDocument).toHaveCount(1, { timeout: 15000 });
  });
});
