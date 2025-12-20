/**
 * Credential Issuance E2E Tests
 *
 * Tests the complete credential issuance flow from approved application:
 * 1. Admin reviews and approves application
 * 2. System issues credential to applicant's mobile wallet
 * 3. Mobile wallet receives and stores credential
 * 4. Credential verification
 * 
 * Uses WalletBridge for postMessage-based wallet coordination.
 *
 * NOTE: These tests require backend API endpoints (/api/test/setup-credential)
 * and UI components that are not yet implemented. Skip until infrastructure is ready.
 */

const { test, expect } = require("@playwright/test");
const {
  waitForElement,
  loginAs,
  WalletBridge,
  PushNotificationHelpers,
  DeviceRegistrationHelpers,
} = require("../utils/test-helpers");
const { SEEDED_USERS, SEEDED_PASSWORDS, SEEDED_ORGS } = require("../fixtures/users");

// Test data for credential issuance
const TEST_APPLICATION = {
  firstName: "Maria",
  lastName: "Credentialist",
  email: "maria.credential@example.com",
  documentType: "PASSPORT",
  birthDate: "1988-07-20",
  nationality: "US",
  travelPurpose: "BUSINESS",
  destinationCountry: "UK",
  travelDate: "2025-06-15",
  returnDate: "2025-06-30",
};

// Skip this test suite - requires backend API endpoints that are not yet implemented
test.describe.skip("Credential Issuance Flow", () => {
  let vendorPage;
  let walletBridge;
  let pushHelpers;
  let deviceHelpers;
  let registeredDeviceId;

  test.beforeAll(async ({ browser }) => {
    // Pre-register device for credential recipient with RSA keypair
    const context = await browser.newContext();
    const page = await context.newPage();

    deviceHelpers = new DeviceRegistrationHelpers(page);
    pushHelpers = new PushNotificationHelpers(page, deviceHelpers);

    // Register test device for the applicant with RSA keypair
    const result = await deviceHelpers.registerDevice(SEEDED_USERS.applicant1.email, {
      platform: "web",
    });
    registeredDeviceId = result.deviceId;

    await context.close();
  });

  test.beforeEach(async ({ page, browser }) => {
    // Create vendor page context for admin actions
    const vendorContext = await browser.newContext();
    vendorPage = await vendorContext.newPage();

    // Initialize wallet bridge for postMessage communication
    walletBridge = new WalletBridge(page, process.env.WALLET_URL || 'http://localhost:5000');
    deviceHelpers = new DeviceRegistrationHelpers(page);
    pushHelpers = new PushNotificationHelpers(page, deviceHelpers);
  });

  test.afterEach(async () => {
    if (vendorPage) {
      await vendorPage.context().close();
    }
  });

  test("should issue credential after application approval", async ({ page }) => {
    // Step 1: Create and submit application as applicant
    await loginAs(page, SEEDED_USERS.applicant1.email, SEEDED_PASSWORDS.applicant);
    await page.goto(`${process.env.APP_URL}/applications/new`);

    // Fill application form
    await page.fill('[data-testid="first-name"]', TEST_APPLICATION.firstName);
    await page.fill('[data-testid="last-name"]', TEST_APPLICATION.lastName);
    await page.fill('[data-testid="birth-date"]', TEST_APPLICATION.birthDate);
    await page.selectOption('[data-testid="document-type"]', TEST_APPLICATION.documentType);
    await page.selectOption('[data-testid="nationality"]', TEST_APPLICATION.nationality);
    await page.selectOption('[data-testid="travel-purpose"]', TEST_APPLICATION.travelPurpose);
    await page.fill('[data-testid="destination-country"]', TEST_APPLICATION.destinationCountry);
    await page.fill('[data-testid="travel-date"]', TEST_APPLICATION.travelDate);
    await page.fill('[data-testid="return-date"]', TEST_APPLICATION.returnDate);

    // Submit application
    await page.click('[data-testid="submit-application"]');
    await waitForElement(page, '[data-testid="application-submitted"]');

    // Get application ID for approval
    const applicationId = await page.getAttribute('[data-testid="application-id"]', "data-value");
    expect(applicationId).toBeTruthy();

    // Step 2: Admin reviews and approves application
    await loginAs(vendorPage, SEEDED_USERS.vendor.email, SEEDED_PASSWORDS.vendor);
    await vendorPage.goto(`${process.env.APP_URL}/admin/applications/${applicationId}`);

    // Verify application details
    await expect(vendorPage.locator('[data-testid="applicant-name"]')).toContainText(
      `${TEST_APPLICATION.firstName} ${TEST_APPLICATION.lastName}`
    );
    await expect(vendorPage.locator('[data-testid="application-status"]')).toContainText("PENDING");

    // Approve application
    await vendorPage.click('[data-testid="approve-application"]');
    await vendorPage.fill(
      '[data-testid="approval-notes"]',
      "Verified documents. Application meets all requirements."
    );
    await vendorPage.click('[data-testid="confirm-approval"]');

    // Wait for approval confirmation
    await waitForElement(vendorPage, '[data-testid="approval-success"]');
    await expect(vendorPage.locator('[data-testid="application-status"]')).toContainText(
      "APPROVED"
    );

    // Step 3: Initiate credential issuance
    await vendorPage.click('[data-testid="issue-credential"]');

    // Select credential type
    await vendorPage.selectOption('[data-testid="credential-type"]', "TRAVEL_AUTHORIZATION");

    // Configure credential attributes
    await vendorPage.fill('[data-testid="credential-validity-days"]', "90");
    await vendorPage.check('[data-testid="include-biometric"]');

    // Issue credential
    await vendorPage.click('[data-testid="confirm-issue-credential"]');
    await waitForElement(vendorPage, '[data-testid="credential-issued"]');

    // Get credential ID
    const credentialId = await vendorPage.getAttribute(
      '[data-testid="credential-id"]',
      "data-value"
    );
    expect(credentialId).toBeTruthy();

    // Step 4: Verify push notification was sent to mobile wallet
    const notifications = await pushHelpers.getNotificationsForUser(
      SEEDED_ORGS.travelCorp.id,
      SEEDED_USERS.applicant1.id
    );

    const credentialNotification = notifications.find(
      (n) => n.type === "CREDENTIAL_ISSUED" && n.credentialId === credentialId
    );
    expect(credentialNotification).toBeTruthy();
    expect(credentialNotification.title).toContain("Travel Authorization Issued");

    // Step 5: Mobile wallet receives credential via WalletBridge
    await walletBridge.init();
    await walletBridge.setDeviceId(registeredDeviceId);

    // Wait for wallet to receive credential
    const credentialReceived = await walletBridge.waitForCredentials(15000);
    const receivedCredential = credentialReceived.find(c => c.credentialId === credentialId);
    expect(receivedCredential).toBeTruthy();
    expect(receivedCredential.type).toBe("TRAVEL_AUTHORIZATION");

    // Step 6: Get stored credentials from wallet
    const storedCredentials = await walletBridge.getCredentials();
    const storedCredential = storedCredentials.find((c) => c.id === credentialId);
    expect(storedCredential).toBeTruthy();
    expect(storedCredential.type).toBe("TRAVEL_AUTHORIZATION");
    expect(storedCredential.issuer).toBe(SEEDED_ORGS.travelCorp.name);
  });

  test("should handle credential offer via QR code", async ({ page }) => {
    // Step 1: Admin generates QR code offer for pre-approved credential
    await loginAs(vendorPage, SEEDED_USERS.vendor.email, SEEDED_PASSWORDS.vendor);
    await vendorPage.goto(`${process.env.APP_URL}/admin/credentials/issue-qr`);

    // Configure credential offer
    await vendorPage.fill('[data-testid="recipient-email"]', TEST_APPLICATION.email);
    await vendorPage.selectOption('[data-testid="credential-type"]', "ACCESS_BADGE");
    await vendorPage.fill('[data-testid="badge-access-level"]', "VISITOR");
    await vendorPage.fill('[data-testid="badge-valid-until"]', "2025-12-31");

    // Generate QR code offer
    await vendorPage.click('[data-testid="generate-qr-offer"]');
    await waitForElement(vendorPage, '[data-testid="qr-code-display"]');

    // Extract QR code data
    const qrCodeData = await vendorPage.getAttribute('[data-testid="qr-code-data"]', "data-value");
    expect(qrCodeData).toBeTruthy();

    // Step 2: Mobile wallet scans QR code using WalletBridge
    await walletBridge.init();
    await walletBridge.setDeviceId(registeredDeviceId);

    // Inject QR code data into wallet scanner
    const scanResult = await walletBridge.scanQrCode(qrCodeData);
    expect(scanResult.success).toBe(true);
    expect(scanResult.type).toBe("ACCESS_BADGE");
    expect(scanResult.issuer).toBe(SEEDED_ORGS.travelCorp.name);

    // Step 3: Wait for credential to be issued and stored
    const storedCredentials = await walletBridge.waitForCredentials(15000);
    const accessBadge = storedCredentials.find(c => c.type === "ACCESS_BADGE");
    expect(accessBadge).toBeTruthy();
    expect(accessBadge.accessLevel).toBe("VISITOR");

    // Step 4: Verify credential appears in admin dashboard as issued
    await vendorPage.goto(`${process.env.APP_URL}/admin/credentials`);
    await vendorPage.fill('[data-testid="search-credentials"]', TEST_APPLICATION.email);
    await vendorPage.click('[data-testid="search-button"]');

    await waitForElement(vendorPage, '[data-testid="credential-row"]');
    await expect(vendorPage.locator('[data-testid="credential-status"]').first()).toContainText(
      "ISSUED"
    );
    await expect(vendorPage.locator('[data-testid="credential-type"]').first()).toContainText(
      "ACCESS_BADGE"
    );
  });

  test("should present credential for verification", async ({ page }) => {
    // Prerequisites: Issue a credential first
    const credentialId = await setupIssuedCredential();

    // Step 1: Verifier requests credential presentation
    await loginAs(page, SEEDED_USERS.verifier.email, SEEDED_PASSWORDS.verifier);
    await page.goto(`${process.env.APP_URL}/verifier/request-presentation`);

    // Configure presentation request
    await page.selectOption('[data-testid="requested-credential-type"]', "TRAVEL_AUTHORIZATION");
    await page.check('[data-testid="require-name"]');
    await page.check('[data-testid="require-validity"]');
    await page.check('[data-testid="require-photo"]', { force: true });

    // Generate presentation request QR
    await page.click('[data-testid="generate-request-qr"]');
    await waitForElement(page, '[data-testid="presentation-request-qr"]');

    const presentationRequestQR = await page.getAttribute(
      '[data-testid="presentation-request-data"]',
      "data-value"
    );

    // Step 2: Mobile wallet scans presentation request
    await walletHelpers.loadWallet();
    await walletHelpers.injectQRCode(presentationRequestQR);

    // Wait for request to be parsed
    const requestReceived = await walletHelpers.waitForMessage("presentation-request-received", 10000);
    expect(requestReceived.requiredAttributes).toContain("name");
    expect(requestReceived.requiredAttributes).toContain("validity");
    expect(requestReceived.verifier).toBeTruthy();

    // Step 3: User selects credential and approves presentation
    await walletHelpers.sendCommand("selectCredentialForPresentation", {
      requestId: requestReceived.requestId,
      credentialId: credentialId,
    });

    // Confirm which attributes to share
    await walletHelpers.sendCommand("approvePresentation", {
      requestId: requestReceived.requestId,
      sharedAttributes: ["name", "validity", "photo"],
    });

    // Wait for presentation to be created and sent
    const presentationSent = await walletHelpers.waitForMessage("presentation-sent", 15000);
    expect(presentationSent.success).toBe(true);
    expect(presentationSent.presentationId).toBeTruthy();

    // Step 4: Verifier receives and validates presentation
    await page.waitForSelector('[data-testid="presentation-received"]', { timeout: 20000 });
    await expect(page.locator('[data-testid="verification-status"]')).toContainText("VALID");
    await expect(page.locator('[data-testid="presented-name"]')).toContainText(
      `${TEST_APPLICATION.firstName} ${TEST_APPLICATION.lastName}`
    );
    await expect(page.locator('[data-testid="credential-valid"]')).toContainText("Yes");
    await expect(page.locator('[data-testid="issuer-verified"]')).toContainText(
      SEEDED_ORGS.travelCorp.name
    );

    // Helper function to set up an issued credential
    async function setupIssuedCredential() {
      // This would typically call the API directly to create a test credential
      const response = await page.request.post(
        `${process.env.API_URL}/api/test/setup-credential`,
        {
          data: {
            recipientUserId: SEEDED_USERS.applicant1.id,
            type: "TRAVEL_AUTHORIZATION",
            attributes: {
              firstName: TEST_APPLICATION.firstName,
              lastName: TEST_APPLICATION.lastName,
              validUntil: "2025-12-31",
              nationality: TEST_APPLICATION.nationality,
            },
          },
          headers: {
            Authorization: `Bearer ${process.env.TEST_ADMIN_TOKEN}`,
          },
        }
      );

      const data = await response.json();
      return data.credentialId;
    }
  });

  test("should revoke issued credential", async ({ page }) => {
    // Step 1: Create and issue credential
    await loginAs(vendorPage, SEEDED_USERS.vendor.email, SEEDED_PASSWORDS.vendor);
    await vendorPage.goto(`${process.env.APP_URL}/admin/credentials/issue`);

    // Quick issue a test credential
    await vendorPage.fill('[data-testid="recipient-email"]', SEEDED_USERS.applicant2.email);
    await vendorPage.selectOption('[data-testid="credential-type"]', "VISITOR_PASS");
    await vendorPage.click('[data-testid="issue-credential"]');

    await waitForElement(vendorPage, '[data-testid="credential-issued"]');
    const credentialId = await vendorPage.getAttribute(
      '[data-testid="credential-id"]',
      "data-value"
    );

    // Step 2: Navigate to credential management and revoke
    await vendorPage.goto(`${process.env.APP_URL}/admin/credentials/${credentialId}`);
    await expect(vendorPage.locator('[data-testid="credential-status"]')).toContainText("ACTIVE");

    await vendorPage.click('[data-testid="revoke-credential"]');
    await vendorPage.fill('[data-testid="revocation-reason"]', "Security policy violation");
    await vendorPage.click('[data-testid="confirm-revoke"]');

    await waitForElement(vendorPage, '[data-testid="revocation-success"]');
    await expect(vendorPage.locator('[data-testid="credential-status"]')).toContainText("REVOKED");

    // Step 3: Verify push notification sent about revocation
    const notifications = await pushHelpers.getNotificationsForUser(
      SEEDED_ORGS.travelCorp.id,
      SEEDED_USERS.applicant2.id
    );

    const revocationNotification = notifications.find(
      (n) => n.type === "CREDENTIAL_REVOKED" && n.credentialId === credentialId
    );
    expect(revocationNotification).toBeTruthy();
    expect(revocationNotification.title).toContain("Credential Revoked");
    expect(revocationNotification.body).toContain("Security policy violation");

    // Step 4: Mobile wallet receives revocation and updates credential status
    await walletHelpers.loadWallet();

    const revocationReceived = await walletHelpers.waitForMessage("credential-revoked", 15000);
    expect(revocationReceived.credentialId).toBe(credentialId);
    expect(revocationReceived.reason).toBe("Security policy violation");

    // Verify credential shows as revoked in wallet
    await walletHelpers.sendCommand("getCredentialStatus", { credentialId });
    const status = await walletHelpers.waitForMessage("credential-status", 5000);
    expect(status.status).toBe("REVOKED");
    expect(status.revokedAt).toBeTruthy();
  });

  test("should handle batch credential issuance", async ({ page }) => {
    // Step 1: Admin prepares batch issuance
    await loginAs(vendorPage, SEEDED_USERS.vendor.email, SEEDED_PASSWORDS.vendor);
    await vendorPage.goto(`${process.env.APP_URL}/admin/credentials/batch-issue`);

    // Upload CSV with recipients
    const csvContent = `email,type,accessLevel,validDays
batch1@example.com,ACCESS_BADGE,STANDARD,30
batch2@example.com,ACCESS_BADGE,STANDARD,30
batch3@example.com,ACCESS_BADGE,VIP,60`;

    // Create file for upload
    await vendorPage.setInputFiles('[data-testid="batch-csv-upload"]', {
      name: "batch-recipients.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(csvContent),
    });

    // Preview batch
    await vendorPage.click('[data-testid="preview-batch"]');
    await waitForElement(vendorPage, '[data-testid="batch-preview"]');

    await expect(vendorPage.locator('[data-testid="batch-count"]')).toContainText("3 credentials");

    // Step 2: Execute batch issuance
    await vendorPage.click('[data-testid="execute-batch"]');

    // Wait for batch processing
    await vendorPage.waitForSelector('[data-testid="batch-progress"]', { state: "visible" });
    await vendorPage.waitForSelector('[data-testid="batch-complete"]', { timeout: 60000 });

    // Verify batch results
    await expect(vendorPage.locator('[data-testid="batch-success-count"]')).toContainText("3");
    await expect(vendorPage.locator('[data-testid="batch-error-count"]')).toContainText("0");

    // Step 3: Verify all credentials appear in the system
    await vendorPage.goto(`${process.env.APP_URL}/admin/credentials`);
    await vendorPage.fill('[data-testid="filter-issued-today"]', "true");
    await vendorPage.click('[data-testid="apply-filters"]');

    // Should see at least 3 new credentials
    const credentialRows = await vendorPage.locator('[data-testid="credential-row"]').count();
    expect(credentialRows).toBeGreaterThanOrEqual(3);
  });

  test("should handle credential with embedded proof", async ({ page }) => {
    // Step 1: Issue credential with cryptographic proof
    await loginAs(vendorPage, SEEDED_USERS.vendor.email, SEEDED_PASSWORDS.vendor);
    await vendorPage.goto(`${process.env.APP_URL}/admin/credentials/issue-with-proof`);

    await vendorPage.fill('[data-testid="recipient-email"]', SEEDED_USERS.applicant1.email);
    await vendorPage.selectOption('[data-testid="credential-type"]', "VERIFIED_IDENTITY");
    await vendorPage.selectOption('[data-testid="proof-type"]', "BBS_PLUS_2020");

    // Add identity claims
    await vendorPage.fill('[data-testid="claim-full-name"]', "Maria Credentialist");
    await vendorPage.fill('[data-testid="claim-date-of-birth"]', "1988-07-20");
    await vendorPage.fill('[data-testid="claim-document-number"]', "A12345678");

    await vendorPage.click('[data-testid="issue-with-proof"]');
    await waitForElement(vendorPage, '[data-testid="credential-issued"]');

    const credentialId = await vendorPage.getAttribute(
      '[data-testid="credential-id"]',
      "data-value"
    );

    // Step 2: Mobile wallet receives credential with proof
    await walletHelpers.loadWallet();

    const credentialReceived = await walletHelpers.waitForMessage("credential-received", 15000);
    expect(credentialReceived.credentialId).toBe(credentialId);
    expect(credentialReceived.proofType).toBe("BBS_PLUS_2020");
    expect(credentialReceived.hasSelectiveDisclosure).toBe(true);

    // Step 3: Accept and verify proof integrity
    await walletHelpers.sendCommand("acceptCredential", { credentialId });
    const accepted = await walletHelpers.waitForMessage("credential-accepted", 10000);
    expect(accepted.proofVerified).toBe(true);

    // Step 4: Create selective disclosure presentation
    await walletHelpers.sendCommand("createSelectivePresentation", {
      credentialId,
      disclosedClaims: ["full-name"], // Only reveal name, hide DOB and document number
    });

    const presentation = await walletHelpers.waitForMessage("selective-presentation-created", 10000);
    expect(presentation.disclosedClaims).toEqual(["full-name"]);
    expect(presentation.hiddenClaims).toContain("date-of-birth");
    expect(presentation.hiddenClaims).toContain("document-number");
    expect(presentation.proof).toBeTruthy();
  });
});

test.describe.skip("Credential Lifecycle Edge Cases", () => {
  let walletHelpers;

  test.beforeEach(async ({ page }) => {
    walletHelpers = new MobileWalletHelpers(page);
  });

  test("should handle expired credential gracefully", async ({ page }) => {
    // Setup: Create an already-expired credential via test API
    const response = await page.request.post(
      `${process.env.API_URL}/api/test/setup-expired-credential`,
      {
        data: {
          recipientUserId: SEEDED_USERS.applicant1.id,
          type: "TRAVEL_AUTHORIZATION",
          expiredAt: "2020-01-01",
        },
        headers: {
          Authorization: `Bearer ${process.env.TEST_ADMIN_TOKEN}`,
        },
      }
    );

    const { credentialId } = await response.json();

    // Load wallet and check credential status
    await walletHelpers.loadWallet();
    await walletHelpers.sendCommand("getCredentialStatus", { credentialId });

    const status = await walletHelpers.waitForMessage("credential-status", 5000);
    expect(status.status).toBe("EXPIRED");
    expect(status.canBeUsed).toBe(false);

    // Attempt to create presentation with expired credential
    await walletHelpers.sendCommand("createPresentation", { credentialId });

    const presentationError = await walletHelpers.waitForMessage("presentation-error", 5000);
    expect(presentationError.error).toBe("CREDENTIAL_EXPIRED");
    expect(presentationError.message).toContain("expired");
  });

  test("should handle network failure during credential issuance", async ({ page }) => {
    // Simulate network failure
    await page.route("**/api/credentials/issue", (route) => route.abort("failed"));

    await loginAs(page, SEEDED_USERS.vendor.email, SEEDED_PASSWORDS.vendor);
    await page.goto(`${process.env.APP_URL}/admin/credentials/issue`);

    await page.fill('[data-testid="recipient-email"]', "test@example.com");
    await page.selectOption('[data-testid="credential-type"]', "ACCESS_BADGE");
    await page.click('[data-testid="issue-credential"]');

    // Should show error message
    await waitForElement(page, '[data-testid="issuance-error"]');
    await expect(page.locator('[data-testid="error-message"]')).toContainText("Network error");
    await expect(page.locator('[data-testid="retry-button"]')).toBeVisible();

    // Remove network block and retry
    await page.unroute("**/api/credentials/issue");
    await page.click('[data-testid="retry-button"]');

    await waitForElement(page, '[data-testid="credential-issued"]');
  });

  test("should queue credential when device is offline", async ({ page }) => {
    // Issue credential when mobile device is offline
    await loginAs(page, SEEDED_USERS.vendor.email, SEEDED_PASSWORDS.vendor);

    // Register device but mark as offline
    const deviceHelpers = new DeviceRegistrationHelpers(page);
    await deviceHelpers.registerDevice({
      deviceId: `${SEEDED_ORGS.travelCorp.id}:offline-device-001`,
      platform: "ios",
      pushToken: "offline-device-token",
    });

    // Simulate device going offline (no heartbeat)
    await page.request.post(`${process.env.API_URL}/api/test/set-device-offline`, {
      data: {
        deviceId: `${SEEDED_ORGS.travelCorp.id}:offline-device-001`,
      },
    });

    // Issue credential
    await page.goto(`${process.env.APP_URL}/admin/credentials/issue`);
    await page.fill('[data-testid="recipient-email"]', SEEDED_USERS.applicant1.email);
    await page.selectOption('[data-testid="credential-type"]', "ACCESS_BADGE");
    await page.click('[data-testid="issue-credential"]');

    await waitForElement(page, '[data-testid="credential-issued"]');
    const credentialId = await page.getAttribute('[data-testid="credential-id"]', "data-value");

    // Credential should be queued for delivery
    await expect(page.locator('[data-testid="delivery-status"]')).toContainText("QUEUED");

    // Simulate device coming back online
    await page.request.post(`${process.env.API_URL}/api/test/set-device-online`, {
      data: {
        deviceId: `${SEEDED_ORGS.travelCorp.id}:offline-device-001`,
      },
    });

    // Load wallet - should receive queued credential
    await walletHelpers.loadWallet();
    await walletHelpers.sendCommand("setTestDeviceId", {
      deviceId: "offline-device-001",
    });

    const credentialReceived = await walletHelpers.waitForMessage("credential-received", 20000);
    expect(credentialReceived.credentialId).toBe(credentialId);
    expect(credentialReceived.wasQueued).toBe(true);
  });
});
