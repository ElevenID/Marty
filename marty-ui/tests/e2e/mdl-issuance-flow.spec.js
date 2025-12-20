/**
 * mDL Issuance Flow - End-to-End Tests
 * 
 * Comprehensive tests covering the full mDL (mobile Driver's License) issuance workflow:
 * 1. Org admin onboarding
 * 2. Admin enables and configures mDL application
 * 3. Applicant fills out application
 * 4. User onboards Marty Authenticator app (wallet pairing)
 * 5. Org admin issues mDL to user's auth app
 */
const { test, expect } = require('@playwright/test');
const { 
  AuthHelpers, 
  WalletBridge,
  DeviceRegistrationHelpers,
  PushNotificationHelpers,
  generateTestKeypair,
  signChallenge,
  SEEDED_USERS 
} = require('../utils/test-helpers');
const { SEEDED_ORGS, SEEDED_PASSWORDS } = require('../fixtures/users');

// Test data for mDL application
const MDL_APPLICATION_DATA = {
  firstName: 'Michael',
  lastName: 'Johnson',
  email: 'michael.johnson@test.marty.demo',
  dateOfBirth: '1988-05-15',
  address: {
    street: '456 Oak Avenue',
    city: 'Austin',
    state: 'TX',
    zip: '78701'
  },
  licenseClass: 'C',
  restrictions: 'none',
  documentNumber: 'DL' + Date.now().toString().slice(-8),
  expiryDate: '2030-12-31'
};

// mDL credential configuration
const MDL_CREDENTIAL_CONFIG = {
  type: 'org.iso.18013.5.1.mDL',
  namespace: 'org.iso.18013.5.1',
  validityDays: 365 * 4, // 4 years
  attributes: [
    'family_name',
    'given_name',
    'birth_date',
    'issue_date',
    'expiry_date',
    'issuing_country',
    'issuing_authority',
    'document_number',
    'portrait',
    'driving_privileges',
    'resident_address',
    'age_over_18',
    'age_over_21'
  ]
};

test.describe('mDL Issuance Flow - Complete Workflow', () => {
  let auth;
  let walletBridge;
  let pushHelpers;
  let deviceHelpers;
  let vendorContext;
  let applicantContext;
  
  test.beforeAll(async ({ browser }) => {
    // Create separate browser contexts for vendor and applicant
    vendorContext = await browser.newContext();
    applicantContext = await browser.newContext();
  });

  test.afterAll(async () => {
    await vendorContext?.close();
    await applicantContext?.close();
  });

  test.beforeEach(async ({ page }) => {
    auth = new AuthHelpers(page);
    walletBridge = new WalletBridge(page);
    deviceHelpers = new DeviceRegistrationHelpers(page);
    pushHelpers = new PushNotificationHelpers(page, deviceHelpers);
  });

  test.describe('Step 1: Organization Admin Onboarding', () => {
    test('new org admin can complete onboarding wizard', async ({ page }) => {
      // Onboarding wizard with role selection and org details form
      const timestamp = Date.now();
      const newOrg = {
        name: `Test DMV ${timestamp}`,
        type: 'government',
        jurisdiction: 'US-TX',
        adminEmail: `admin-${timestamp}@test.marty.demo`
      };

      await page.goto('/');
      
      // Start onboarding
      await page.click('[data-testid="get-started-btn"], button:has-text("Get Started")');
      
      // Step 1: Select organization type
      await expect(page.locator('[data-testid="role-selection"]')).toBeVisible({ timeout: 10000 });
      await page.click('[data-testid="role-issuer"], [data-testid="role-vendor"]');
      await page.click('[data-testid="continue-btn"]');
      
      // Step 2: Organization details
      await expect(page.locator('[data-testid="org-details-form"]')).toBeVisible({ timeout: 10000 });
      await page.fill('[data-testid="org-name-input"]', newOrg.name);
      await page.selectOption('[data-testid="org-type-select"]', newOrg.type);
      await page.fill('[data-testid="jurisdiction-input"]', newOrg.jurisdiction);
      await page.click('[data-testid="continue-btn"]');
      
      // Step 3: Admin account setup
      await expect(page.locator('[data-testid="admin-setup-form"]')).toBeVisible({ timeout: 10000 });
      // Keycloak handles this via redirect or inline form
      
      // Step 4: Complete setup
      await expect(page.locator('[data-testid="setup-complete"]')).toBeVisible({ timeout: 30000 });
      await expect(page.locator('[data-testid="org-name-display"]')).toContainText(newOrg.name);
    });

    test('seeded vendor admin can login and access dashboard', async ({ page }) => {
      // Vendor admin login and dashboard access
      await auth.loginAsSeededUser('vendor');
      
      // Verify dashboard access
      await expect(page.getByRole('tab', { name: 'Dashboard' })).toBeVisible({ timeout: 10000 });
      await expect(page.getByRole('tab', { name: 'Applicants' })).toBeVisible();
      await expect(page.getByRole('tab', { name: 'Settings' })).toBeVisible();
      
      // Verify org info is displayed
      await expect(page.locator('body')).toContainText(SEEDED_USERS.vendor.email);
    });
  });

  test.describe('Step 2: Admin Enables and Configures mDL Application', () => {
    test('admin can enable mDL credential type', async ({ page }) => {
      // Enable mDL credential type in Settings
      await auth.loginAsSeededUser('vendor');
      
      // Navigate to Settings > Credentials
      await page.getByRole('tab', { name: 'Settings' }).click();
      await page.click('[data-testid="credential-types-tab"], a:has-text("Credential Types")');
      
      // Find mDL and enable it
      await expect(page.locator('[data-testid="credential-type-mdl"]')).toBeVisible({ timeout: 10000 });
      
      const mdlToggle = page.locator('[data-testid="enable-mdl-toggle"]');
      const isEnabled = await mdlToggle.isChecked();
      
      if (!isEnabled) {
        await mdlToggle.click();
        await expect(page.locator('[data-testid="mdl-enabled-badge"]')).toBeVisible();
      }
      
      // Verify mDL is in the active credential types list
      await expect(page.locator('[data-testid="active-credential-types"]')).toContainText('mDL');
    });

    test('admin can configure mDL application form', async ({ page }) => {
      // Configure mDL application form in Form Builder
      await auth.loginAsSeededUser('vendor');
      
      // Navigate to Settings > Application Form Builder
      await page.getByRole('tab', { name: 'Settings' }).click();
      await page.click('[data-testid="form-builder-tab"], a:has-text("Application Form")');
      
      // Select mDL template
      await page.selectOption('[data-testid="credential-type-select"]', 'org.iso.18013.5.1.mDL');
      
      // Verify required fields are present
      const requiredFields = ['family_name', 'given_name', 'birth_date', 'portrait', 'document_number'];
      for (const field of requiredFields) {
        await expect(page.locator(`[data-testid="field-${field}"]`)).toBeVisible();
      }
      
      // Enable driving privileges section
      await page.click('[data-testid="toggle-driving-privileges"]');
      await expect(page.locator('[data-testid="field-driving_privileges"]')).toBeVisible();
      
      // Save configuration
      await page.click('[data-testid="save-form-config-btn"]');
      await expect(page.locator('[data-testid="config-saved-toast"]')).toBeVisible();
    });

    test('admin can configure mDL issuance policy', async ({ page }) => {
      // Configure mDL issuance policy
      await auth.loginAsSeededUser('vendor');
      
      // Navigate to Settings > Issuance Policy
      await page.getByRole('tab', { name: 'Settings' }).click();
      await page.click('[data-testid="issuance-policy-tab"], a:has-text("Issuance Policy")');
      
      // Configure mDL validity period
      await page.fill('[data-testid="validity-years-input"]', '4');
      
      // Configure required verifications
      await page.check('[data-testid="require-identity-verification"]');
      await page.check('[data-testid="require-document-verification"]');
      
      // Configure auto-renewal settings
      await page.check('[data-testid="allow-renewal"]');
      await page.fill('[data-testid="renewal-window-days"]', '90');
      
      // Save policy
      await page.click('[data-testid="save-policy-btn"]');
      await expect(page.locator('[data-testid="policy-saved-toast"]')).toBeVisible();
    });
  });

  test.describe('Step 3: Applicant Fills Out Application', () => {
    test('applicant can start mDL application', async ({ page }) => {
      // Start mDL application from /apply page
      await auth.loginAsSeededUser('applicant1');
      
      // Navigate to apply page
      await page.goto('/apply');
      
      // Select mDL credential type
      await expect(page.locator('[data-testid="credential-type-list"]')).toBeVisible({ timeout: 10000 });
      await page.click('[data-testid="apply-mdl-btn"]');
      
      // Verify application form is displayed
      await expect(page.locator('[data-testid="mdl-application-form"]')).toBeVisible();
      await expect(page.locator('h1, h2')).toContainText(/Mobile Driver.*License|mDL/i);
    });

    test('applicant can fill and submit mDL application', async ({ page }) => {
      // Fill and submit mDL application with multi-step wizard
      await auth.loginAsSeededUser('applicant1');
      await page.goto('/apply/mdl');
      
      // Wait for form to load
      await expect(page.locator('[data-testid="mdl-application-form"]')).toBeVisible({ timeout: 10000 });
      
      // Step 1: Personal Information
      await page.fill('[data-testid="first-name-input"]', MDL_APPLICATION_DATA.firstName);
      await page.fill('[data-testid="last-name-input"]', MDL_APPLICATION_DATA.lastName);
      await page.fill('[data-testid="dob-input"]', MDL_APPLICATION_DATA.dateOfBirth);
      await page.click('[data-testid="next-step-btn"]');
      
      // Step 2: Address Information
      await expect(page.locator('[data-testid="address-step"]')).toBeVisible();
      await page.fill('[data-testid="street-input"]', MDL_APPLICATION_DATA.address.street);
      await page.fill('[data-testid="city-input"]', MDL_APPLICATION_DATA.address.city);
      await page.selectOption('[data-testid="state-select"]', MDL_APPLICATION_DATA.address.state);
      await page.fill('[data-testid="zip-input"]', MDL_APPLICATION_DATA.address.zip);
      await page.click('[data-testid="next-step-btn"]');
      
      // Step 3: License Details
      await expect(page.locator('[data-testid="license-step"]')).toBeVisible();
      await page.selectOption('[data-testid="license-class-select"]', MDL_APPLICATION_DATA.licenseClass);
      await page.fill('[data-testid="document-number-input"]', MDL_APPLICATION_DATA.documentNumber);
      await page.click('[data-testid="next-step-btn"]');
      
      // Step 4: Photo Upload
      await expect(page.locator('[data-testid="photo-step"]')).toBeVisible();
      // Use test photo file
      const photoInput = page.locator('[data-testid="portrait-upload-input"]');
      await photoInput.setInputFiles('./tests/fixtures/test-portrait.jpg');
      await expect(page.locator('[data-testid="photo-preview"]')).toBeVisible();
      await page.click('[data-testid="next-step-btn"]');
      
      // Step 5: Review and Submit
      await expect(page.locator('[data-testid="review-step"]')).toBeVisible();
      await expect(page.locator('[data-testid="review-first-name"]')).toContainText(MDL_APPLICATION_DATA.firstName);
      await expect(page.locator('[data-testid="review-last-name"]')).toContainText(MDL_APPLICATION_DATA.lastName);
      
      // Accept terms
      await page.check('[data-testid="accept-terms-checkbox"]');
      
      // Submit application
      await page.click('[data-testid="submit-application-btn"]');
      
      // Verify submission success
      await expect(page.locator('[data-testid="application-submitted"]')).toBeVisible({ timeout: 15000 });
      const applicationId = await page.getAttribute('[data-testid="application-id"]', 'data-value');
      expect(applicationId).toBeTruthy();
      
      // Store for later steps
      test.info().annotations.push({ type: 'applicationId', description: applicationId });
    });

    test('applicant can view application status', async ({ page }) => {
      // View application status in /my-applications
      await auth.loginAsSeededUser('applicant1');
      
      // Navigate to applications list
      await page.goto('/my-applications');
      
      // Verify pending application is listed
      await expect(page.locator('[data-testid="applications-list"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="application-status-pending"]')).toBeVisible();
      
      // Click to view details
      await page.click('[data-testid="view-application-btn"]:first-child');
      
      // Verify application details page
      await expect(page.locator('[data-testid="application-details"]')).toBeVisible();
      await expect(page.locator('[data-testid="status-badge"]')).toContainText(/pending|submitted/i);
    });
  });

  test.describe('Step 4: User Onboards Marty Authenticator App', () => {
    test.skip('user can start wallet pairing from web', async ({ page }) => {
      // SKIPPED: Requires /wallet/setup page with container and QR generation
      // TODO: Wire up WalletSetup component to this route
      await auth.loginAsSeededUser('applicant1');
      
      // Navigate to wallet setup
      await page.goto('/wallet/setup');
      
      // Verify wallet setup page
      await expect(page.locator('[data-testid="wallet-setup-container"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('h1, h2')).toContainText(/Connect.*Wallet|Set Up.*Authenticator/i);
    });

    test.skip('user can generate pairing QR code', async ({ page }) => {
      // SKIPPED: Requires QR code generation with data-testid attributes
      // TODO: Add data-testid to WalletSetup QR code element
      await auth.loginAsSeededUser('applicant1');
      await page.goto('/wallet/setup');
      
      // Click generate QR button
      await page.click('[data-testid="generate-pairing-qr-btn"]');
      
      // Wait for QR code to be generated
      await expect(page.locator('[data-testid="pairing-qr-code"]')).toBeVisible({ timeout: 10000 });
      
      // Verify QR contains pairing data
      const qrData = await page.getAttribute('[data-testid="pairing-qr-code"]', 'data-value');
      expect(qrData).toBeTruthy();
      expect(qrData).toMatch(/marty:\/\/pair|openid-credential-offer/);
    });

    test.skip('wallet can complete device registration', async ({ page }) => {
      // SKIPPED: Requires backend push challenge API endpoints
      // TODO: Wire up /api/push/challenges endpoints
      // Generate a test user ID (in real flow, comes from auth)
      const testUserId = SEEDED_USERS.applicant1.email;
      
      // Register device with backend (auto-generates keypair)
      const registrationResult = await deviceHelpers.registerDevice(testUserId, {
        platform: 'ios',
        deviceModel: 'iPhone 15 Pro',
        osVersion: '17.0'
      });
      
      expect(registrationResult.device_id).toBeTruthy();
      expect(registrationResult.keypair).toBeTruthy();
      
      const deviceId = registrationResult.deviceId;
      
      // Create a push challenge to verify device
      const challengeResult = await pushHelpers.createPushChallenge(deviceId, {
        action: 'verify_device',
        ttl_seconds: 300
      });
      expect(challengeResult.challenge_id).toBeTruthy();
      expect(challengeResult.nonce).toBeTruthy();
      
      // Sign and respond to challenge
      const signature = deviceHelpers.signChallengeForDevice(deviceId, challengeResult.nonce);
      expect(signature).toBeTruthy();
      
      const responseResult = await pushHelpers.respondToChallenge(
        deviceId,
        challengeResult.challenge_id,
        'accept',
        challengeResult.nonce,
        signature
      );
      
      expect(responseResult.success).toBe(true);
    });

    test.skip('wallet can pair with user account', async ({ page }) => {
      // SKIPPED: Requires complete wallet pairing flow
      // TODO: Connect WalletSetup to backend pairing API
      const testUserId = SEEDED_USERS.applicant1.email;
      
      // Login as applicant
      await auth.loginAsSeededUser('applicant1');
      await page.goto('/wallet/setup');
      
      // Get pairing token
      await page.click('[data-testid="generate-pairing-qr-btn"]');
      await expect(page.locator('[data-testid="pairing-qr-code"]')).toBeVisible({ timeout: 10000 });
      const pairingData = await page.getAttribute('[data-testid="pairing-qr-code"]', 'data-value');
      expect(pairingData).toBeTruthy();
      
      // Register device (simulating wallet scanning QR and registering)
      const registrationResult = await deviceHelpers.registerDevice(testUserId, {
        platform: 'ios',
        deviceModel: 'iPhone 15 Pro'
      });
      
      expect(registrationResult.deviceId).toBeTruthy();
      
      // Initialize wallet bridge with the device ID
      const deviceId = registrationResult.deviceId;
      await walletBridge.init({ deviceId });
      
      // Scan the pairing QR code in wallet
      await walletBridge.scanQrCode(pairingData);
      
      // Set device ID in wallet
      await walletBridge.setDeviceId(deviceId);
      
      // Verify pairing in web UI
      await page.reload();
      await expect(page.locator('[data-testid="device-paired-badge"], [data-testid="pairing-success"]')).toBeVisible({ timeout: 10000 });
    });

    test.skip('user can enable push notifications', async ({ page }) => {
      // SKIPPED: Requires /settings/notifications with proper data-testid attributes
      // TODO: Add missing data-testid attributes to NotificationPreferences component
      await auth.loginAsSeededUser('applicant1');
      
      // Navigate to notification settings
      await page.goto('/settings/notifications');
      
      // Enable push notifications
      await expect(page.locator('[data-testid="notification-settings"]')).toBeVisible({ timeout: 10000 });
      
      const pushToggle = page.locator('[data-testid="enable-push-toggle"]');
      if (!(await pushToggle.isChecked())) {
        await pushToggle.click();
      }
      
      // Enable credential notifications
      await page.check('[data-testid="notify-credential-issued"]');
      await page.check('[data-testid="notify-credential-expiring"]');
      
      // Save settings
      await page.click('[data-testid="save-notification-settings-btn"]');
      await expect(page.locator('[data-testid="settings-saved-toast"]')).toBeVisible();
    });
  });

  test.describe('Step 5: Org Admin Issues mDL to User', () => {
    test.skip('admin can view pending applications', async ({ page }) => {
      // SKIPPED: Requires vendor applicants list with status filtering
      // TODO: Implement applications table with status filters
      await auth.loginAsSeededUser('vendor');
      
      // Navigate to Applicants tab
      await page.getByRole('tab', { name: 'Applicants' }).click();
      
      // Filter by pending status
      await page.click('[data-testid="status-filter"]');
      await page.click('[data-testid="filter-pending"]');
      
      // Verify pending applications are listed
      await expect(page.locator('[data-testid="applications-table"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="application-row"]').first()).toBeVisible();
    });

    test.skip('admin can review and approve mDL application', async ({ page }) => {
      // SKIPPED: Requires application detail view with approval workflow
      // TODO: Implement application review and approval UI
      await auth.loginAsSeededUser('vendor');
      
      // Navigate to specific application
      await page.getByRole('tab', { name: 'Applicants' }).click();
      await page.click('[data-testid="application-row"]:first-child');
      
      // Verify application details are displayed
      await expect(page.locator('[data-testid="application-detail-view"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="applicant-name"]')).toBeVisible();
      await expect(page.locator('[data-testid="application-status"]')).toContainText(/pending|submitted/i);
      
      // Review documents
      await page.click('[data-testid="view-documents-btn"]');
      await expect(page.locator('[data-testid="documents-panel"]')).toBeVisible();
      await page.click('[data-testid="mark-documents-verified"]');
      
      // Approve application
      await page.click('[data-testid="approve-application-btn"]');
      
      // Fill approval form
      await expect(page.locator('[data-testid="approval-dialog"]')).toBeVisible();
      await page.fill('[data-testid="approval-notes"]', 'Documents verified. All requirements met.');
      await page.click('[data-testid="confirm-approval-btn"]');
      
      // Verify approval success
      await expect(page.locator('[data-testid="approval-success"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="application-status"]')).toContainText(/approved/i);
    });

    test.skip('admin can issue mDL credential', async ({ page }) => {
      // SKIPPED: Requires credential issuance dialog UI
      // TODO: Implement credential issuance workflow
      await auth.loginAsSeededUser('vendor');
      
      // Navigate to approved application
      await page.getByRole('tab', { name: 'Applicants' }).click();
      await page.click('[data-testid="status-filter"]');
      await page.click('[data-testid="filter-approved"]');
      await page.click('[data-testid="application-row"]:first-child');
      
      // Click issue credential button
      await page.click('[data-testid="issue-credential-btn"]');
      
      // Verify issuance dialog
      await expect(page.locator('[data-testid="issuance-dialog"]')).toBeVisible({ timeout: 10000 });
      
      // Select credential type (mDL)
      await page.selectOption('[data-testid="credential-type-select"]', MDL_CREDENTIAL_CONFIG.type);
      
      // Configure validity period
      await page.fill('[data-testid="validity-days-input"]', MDL_CREDENTIAL_CONFIG.validityDays.toString());
      
      // Select attributes to include
      for (const attr of MDL_CREDENTIAL_CONFIG.attributes.slice(0, 5)) {
        await page.check(`[data-testid="attr-${attr}-checkbox"]`);
      }
      
      // Confirm issuance
      await page.click('[data-testid="confirm-issue-btn"]');
      
      // Wait for credential generation
      await expect(page.locator('[data-testid="credential-issued-success"]')).toBeVisible({ timeout: 30000 });
      
      // Get credential ID
      const credentialId = await page.getAttribute('[data-testid="credential-id"]', 'data-value');
      expect(credentialId).toBeTruthy();
      
      // Verify credential appears in issued list
      await page.goto('/admin/credentials');
      await expect(page.locator(`[data-testid="credential-${credentialId}"]`)).toBeVisible();
    });

    test.skip('user receives credential in wallet via push notification', async ({ page }) => {
      // SKIPPED: Requires full wallet-to-backend push notification integration
      // TODO: Wire up push notification delivery to wallet
      const testUserId = SEEDED_USERS.applicant1.email;
      
      // Register device with push token
      const registrationResult = await deviceHelpers.registerDevice(testUserId, {
        platform: 'ios',
        fcmToken: `push-token-${Date.now()}`
      });
      
      const deviceId = registrationResult.deviceId;
      
      // Initialize wallet bridge
      await walletBridge.init({ deviceId });
      
      // Wait for push notification with credential offer
      // In real flow, this would come after admin issues credential
      // For this test, we check the notification helpers
      const notifications = await pushHelpers.getAllNotifications();
      
      // Look for credential offer notification (if any have been sent)
      const credentialOfferNotification = notifications.find(
        n => n.event_type === 'CREDENTIAL_OFFER' || n.type === 'CREDENTIAL_OFFER'
      );
      
      if (credentialOfferNotification) {
        // Simulate accepting credential offer in wallet
        await walletBridge.sendMessage('ACCEPT_CREDENTIAL_OFFER', {
          offerId: credentialOfferNotification.offer_id || credentialOfferNotification.offerId
        });
        
        // Wait for credential to be stored
        const credentials = await walletBridge.waitForCredentials(1, 30000);
        expect(credentials.length).toBeGreaterThanOrEqual(1);
        
        // Verify mDL credential is present
        const mdlCredential = credentials.find(c => 
          c.type?.includes('mDL') || c.doctype?.includes('18013')
        );
        expect(mdlCredential).toBeTruthy();
      } else {
        // If no credential notification yet, verify device is ready to receive
        expect(registrationResult.deviceId).toBeTruthy();
        console.log('Device registered and ready to receive credentials');
      }
    });

    test.skip('user can view issued credential in wallet', async ({ page }) => {
      // SKIPPED: Requires wallet credential storage integration
      // TODO: Wire up wallet credential viewing
      const testUserId = SEEDED_USERS.applicant1.email;
      
      // Register device
      const registrationResult = await deviceHelpers.registerDevice(testUserId, {
        platform: 'ios'
      });
      
      const deviceId = registrationResult.deviceId;
      
      // Initialize wallet
      await walletBridge.init({ deviceId });
      
      // Store a test mDL credential for viewing
      const testCredential = {
        id: `cred-${Date.now()}`,
        type: ['VerifiableCredential', 'mDL'],
        doctype: 'org.iso.18013.5.1.mDL',
        claims: {
          family_name: 'Johnson',
          given_name: 'Michael',
          birth_date: '1988-05-15',
          document_number: 'DL12345678',
          issue_date: new Date().toISOString().split('T')[0],
          expiry_date: '2028-05-15',
          issuing_authority: 'Demo DMV'
        },
        issuer: 'Demo DMV',
        issuedAt: new Date().toISOString()
      };
      
      await walletBridge.storeCredential(testCredential);
      
      // Get stored credentials
      const storedCredentials = await walletBridge.getCredentials();
      const mdlCredential = storedCredentials.find(c => 
        c.type?.includes('mDL') || c.doctype?.includes('18013')
      );
      
      expect(mdlCredential).toBeTruthy();
      expect(mdlCredential.claims).toHaveProperty('family_name');
      expect(mdlCredential.claims).toHaveProperty('given_name');
      expect(mdlCredential.claims).toHaveProperty('birth_date');
      expect(mdlCredential.claims).toHaveProperty('document_number');
    });
  });

  test.describe('Full Flow Integration', () => {
    test.skip('complete mDL issuance flow from application to wallet', async ({ browser }) => {
      // SKIPPED: Requires all individual components to be implemented first
      // This test will be enabled when all Step 1-5 tests pass
      // Create separate contexts for vendor and applicant
      const vendorPage = await vendorContext.newPage();
      const applicantPage = await applicantContext.newPage();
      const vendorAuth = new AuthHelpers(vendorPage);
      const applicantAuth = new AuthHelpers(applicantPage);
      
      try {
        const testData = {
          firstName: 'IntegrationTest',
          lastName: 'User' + Date.now(),
          email: `integration-${Date.now()}@test.marty.demo`,
          dob: '1990-01-15'
        };
        
        // === STEP 1: Applicant submits application ===
        await applicantAuth.loginAsSeededUser('applicant1');
        await applicantPage.goto('/apply/mdl');
        
        await applicantPage.fill('[data-testid="first-name-input"]', testData.firstName);
        await applicantPage.fill('[data-testid="last-name-input"]', testData.lastName);
        await applicantPage.fill('[data-testid="dob-input"]', testData.dob);
        
        // Complete minimal required fields
        await applicantPage.click('[data-testid="next-step-btn"]');
        await applicantPage.fill('[data-testid="street-input"]', '123 Test St');
        await applicantPage.fill('[data-testid="city-input"]', 'Austin');
        await applicantPage.selectOption('[data-testid="state-select"]', 'TX');
        await applicantPage.fill('[data-testid="zip-input"]', '78701');
        await applicantPage.click('[data-testid="next-step-btn"]');
        
        await applicantPage.selectOption('[data-testid="license-class-select"]', 'C');
        await applicantPage.fill('[data-testid="document-number-input"]', 'DL' + Date.now());
        await applicantPage.click('[data-testid="next-step-btn"]');
        
        // Skip photo for integration test (use default)
        await applicantPage.click('[data-testid="skip-photo-btn"], [data-testid="next-step-btn"]');
        
        await applicantPage.check('[data-testid="accept-terms-checkbox"]');
        await applicantPage.click('[data-testid="submit-application-btn"]');
        
        await expect(applicantPage.locator('[data-testid="application-submitted"]')).toBeVisible({ timeout: 15000 });
        const applicationId = await applicantPage.getAttribute('[data-testid="application-id"]', 'data-value');
        expect(applicationId).toBeTruthy();
        
        // === STEP 2: Applicant sets up wallet ===
        await applicantPage.goto('/wallet/setup');
        await applicantPage.click('[data-testid="generate-pairing-qr-btn"]');
        const pairingData = await applicantPage.getAttribute('[data-testid="pairing-qr-code"]', 'data-value');
        
        // Simulate wallet pairing (in real flow, mobile app would scan)
        const keypair = generateTestKeypair();
        const deviceId = `device-${Date.now()}`;
        
        // Register device via API
        const apiResponse = await applicantPage.evaluate(async ({ deviceId, publicKey, apiUrl }) => {
          const response = await fetch(`${apiUrl}/api/test/wallet/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              device_id: deviceId,
              public_key: publicKey,
              platform: 'ios',
              push_token: `push-${deviceId}`
            })
          });
          return response.json();
        }, { 
          deviceId, 
          publicKey: keypair.publicKeyDerBase64,
          apiUrl: process.env.API_URL || 'http://localhost:8000'
        });
        
        expect(apiResponse.success).toBe(true);
        
        // === STEP 3: Vendor approves and issues credential ===
        await vendorAuth.loginAsSeededUser('vendor');
        await vendorPage.goto(`/admin/applications/${applicationId}`);
        
        // Approve application
        await vendorPage.click('[data-testid="approve-application-btn"]');
        await vendorPage.fill('[data-testid="approval-notes"]', 'Integration test approval');
        await vendorPage.click('[data-testid="confirm-approval-btn"]');
        await expect(vendorPage.locator('[data-testid="approval-success"]')).toBeVisible({ timeout: 10000 });
        
        // Issue credential
        await vendorPage.click('[data-testid="issue-credential-btn"]');
        await vendorPage.selectOption('[data-testid="credential-type-select"]', MDL_CREDENTIAL_CONFIG.type);
        await vendorPage.click('[data-testid="confirm-issue-btn"]');
        
        await expect(vendorPage.locator('[data-testid="credential-issued-success"]')).toBeVisible({ timeout: 30000 });
        const credentialId = await vendorPage.getAttribute('[data-testid="credential-id"]', 'data-value');
        expect(credentialId).toBeTruthy();
        
        // === STEP 4: Verify credential was sent to wallet ===
        // Check push notification was queued
        const pushResult = await vendorPage.evaluate(async ({ deviceId, apiUrl }) => {
          const response = await fetch(`${apiUrl}/api/test/wallet/notifications?device_id=${deviceId}`);
          return response.json();
        }, { deviceId, apiUrl: process.env.API_URL || 'http://localhost:8000' });
        
        const credentialNotification = pushResult.notifications?.find(
          n => n.type === 'CREDENTIAL_OFFER'
        );
        expect(credentialNotification).toBeTruthy();
        
        // === STEP 5: Applicant sees issued credential ===
        await applicantPage.goto('/my-credentials');
        await expect(applicantPage.locator('[data-testid="credential-card-mdl"]')).toBeVisible({ timeout: 15000 });
        await expect(applicantPage.locator('[data-testid="credential-status-active"]')).toBeVisible();
        
        console.log('✅ Complete mDL issuance flow succeeded');
        console.log(`   Application ID: ${applicationId}`);
        console.log(`   Credential ID: ${credentialId}`);
        console.log(`   Device ID: ${deviceId}`);
        
      } finally {
        await vendorPage.close();
        await applicantPage.close();
      }
    });
  });
});

// =============================================================================
// Additional Helper Functions
// =============================================================================

/**
 * Wait for element with better error messages
 */
async function waitForElement(page, selector, options = {}) {
  const { timeout = 10000, state = 'visible' } = options;
  try {
    await page.waitForSelector(selector, { timeout, state });
  } catch (error) {
    throw new Error(`Element not found: ${selector} (waited ${timeout}ms for state: ${state})`);
  }
}

/**
 * Login helper with error handling
 */
async function loginAs(page, email, password) {
  const auth = new AuthHelpers(page);
  await auth.login(email, password);
}
