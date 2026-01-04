/**
 * OID4VP (OpenID for Verifiable Presentations) E2E Tests
 *
 * Tests the complete presentation flow:
 * 1. Verifier creates a presentation request
 * 2. Wallet receives and parses the request
 * 3. User selects credentials and approves disclosure
 * 4. Wallet generates verifiable presentation
 * 5. Verifier validates the presentation
 *
 * Uses WalletBridge for postMessage-based wallet coordination.
 *
 * NOTE: These tests require backend API endpoints and wallet integration
 * that are not yet implemented. Skip until infrastructure is ready.
 */

const { test, expect } = require("@playwright/test");
const {
  AuthHelpers,
  WalletBridge,
  DeviceRegistrationHelpers,
  PushNotificationHelpers,
  SEEDED_USERS,
  SEEDED_PASSWORDS,
  SEEDED_ORGS,
} = require("../../utils/test-helpers");

// Skip this test suite - requires OID4VP endpoints and wallet integration
test.describe.skip("OID4VP Presentation Flow", () => {
  let walletBridge;
  let deviceHelpers;
  let pushHelpers;
  let deviceId;
  let credentialId;

  test.beforeAll(async ({ browser }) => {
    // Pre-setup: Register device and issue a test credential
    const context = await browser.newContext();
    const page = await context.newPage();

    deviceHelpers = new DeviceRegistrationHelpers(page);
    pushHelpers = new PushNotificationHelpers(page, deviceHelpers);

    // Register device with RSA keypair
    const result = await deviceHelpers.registerDevice(SEEDED_USERS.applicant1.email, {
      platform: "web",
    });
    deviceId = result.deviceId;

    await context.close();
  });

  test.beforeEach(async ({ page }) => {
    walletBridge = new WalletBridge(page, process.env.WALLET_URL || "http://localhost:5000");
    deviceHelpers = new DeviceRegistrationHelpers(page);
    pushHelpers = new PushNotificationHelpers(page, deviceHelpers);
  });

  test("should handle presentation request via QR code", async ({ page, browser }) => {
    // Step 1: Verifier creates presentation request
    const verifierContext = await browser.newContext();
    const verifierPage = await verifierContext.newPage();
    const verifierAuth = new AuthHelpers(verifierPage);

    await verifierPage.goto("/");
    await verifierAuth.login(SEEDED_USERS.verifier.email, SEEDED_PASSWORDS.verifier);

    // Navigate to create presentation request
    await verifierPage.goto("/verifier/create-request");
    await verifierPage.waitForSelector('[data-testid="presentation-request-form"]');

    // Configure presentation request for mDL
    await verifierPage.selectOption('[data-testid="requested-credential-type"]', "org.iso.18013.5.1.mDL");
    await verifierPage.check('[data-testid="claim-given_name"]');
    await verifierPage.check('[data-testid="claim-family_name"]');
    await verifierPage.check('[data-testid="claim-birth_date"]');
    await verifierPage.fill('[data-testid="request-nonce"]', `nonce-${Date.now()}`);

    // Generate QR code
    await verifierPage.click('[data-testid="generate-presentation-qr"]');
    await verifierPage.waitForSelector('[data-testid="presentation-qr-code"]');

    // Extract QR code data
    const presentationRequestUri = await verifierPage.getAttribute(
      '[data-testid="presentation-qr-data"]',
      "data-value"
    );
    expect(presentationRequestUri).toBeTruthy();
    expect(presentationRequestUri).toMatch(/^openid4vp:\/\//);

    // Get request ID for verification
    const requestId = await verifierPage.getAttribute('[data-testid="request-id"]', "data-value");

    // Step 2: Wallet scans QR and receives request
    await walletBridge.init();
    await walletBridge.setDeviceId(deviceId);

    const scanResult = await walletBridge.scanQrCode(presentationRequestUri);
    expect(scanResult.success).toBe(true);
    expect(scanResult.type).toBe("PRESENTATION_REQUEST");
    expect(scanResult.requestedCredential).toBe("org.iso.18013.5.1.mDL");
    expect(scanResult.requestedClaims).toContain("given_name");
    expect(scanResult.requestedClaims).toContain("family_name");
    expect(scanResult.requestedClaims).toContain("birth_date");

    // Step 3: Wallet presents credential (auto-approved in test mode)
    // In production, this would require user interaction
    const presentationResult = await walletBridge._waitForMessage("PRESENTATION_SUBMITTED", 15000);
    expect(presentationResult.success).toBe(true);
    expect(presentationResult.presentedClaims).toHaveProperty("given_name");
    expect(presentationResult.presentedClaims).toHaveProperty("family_name");
    expect(presentationResult.presentedClaims).toHaveProperty("birth_date");

    // Step 4: Verifier receives and validates presentation
    await verifierPage.goto(`/verifier/requests/${requestId}`);
    await verifierPage.waitForSelector('[data-testid="presentation-received"]');

    // Check presentation status
    await expect(verifierPage.locator('[data-testid="presentation-status"]')).toContainText("VERIFIED");
    await expect(verifierPage.locator('[data-testid="presented-given_name"]')).toBeVisible();
    await expect(verifierPage.locator('[data-testid="presented-family_name"]')).toBeVisible();
    await expect(verifierPage.locator('[data-testid="presented-birth_date"]')).toBeVisible();

    await verifierContext.close();
  });

  test("should handle presentation request via push notification", async ({ page, browser }) => {
    // Step 1: Verifier creates remote presentation request
    const verifierContext = await browser.newContext();
    const verifierPage = await verifierContext.newPage();
    const verifierAuth = new AuthHelpers(verifierPage);

    await verifierPage.goto("/");
    await verifierAuth.login(SEEDED_USERS.verifier.email, SEEDED_PASSWORDS.verifier);

    // Navigate to remote verification
    await verifierPage.goto("/verifier/remote-request");
    await verifierPage.waitForSelector('[data-testid="remote-request-form"]');

    // Enter holder's device ID (in production, this might be looked up)
    await verifierPage.fill('[data-testid="holder-device-id"]', deviceId);
    await verifierPage.selectOption('[data-testid="requested-credential-type"]', "org.iso.18013.5.1.mDL");
    await verifierPage.check('[data-testid="claim-given_name"]');

    // Send request via push
    await verifierPage.click('[data-testid="send-presentation-request"]');
    await verifierPage.waitForSelector('[data-testid="request-sent"]');

    const requestId = await verifierPage.getAttribute('[data-testid="request-id"]', "data-value");
    const nonce = await verifierPage.getAttribute('[data-testid="request-nonce"]', "data-value");

    // Step 2: Wallet receives push challenge
    await walletBridge.init();
    await walletBridge.setDeviceId(deviceId);

    // Inject the presentation challenge (simulates push notification)
    const challengeResult = await walletBridge.injectChallenge({
      type: "PRESENTATION_REQUEST",
      requestId,
      nonce,
      credential_type: "org.iso.18013.5.1.mDL",
      requested_claims: ["given_name"],
      verifier: SEEDED_ORGS.travelCorp.name,
    });
    expect(challengeResult.received).toBe(true);

    // Step 3: Wallet responds with presentation
    const presentationResult = await walletBridge._waitForMessage("PRESENTATION_SUBMITTED", 15000);
    expect(presentationResult.success).toBe(true);

    // Step 4: Create push challenge response with signature
    const result = await pushHelpers.respondToChallenge(
      deviceId,
      challengeResult.challengeId,
      "accept",
      nonce
    );
    expect(result.success).toBe(true);

    // Step 5: Verify presentation received by verifier
    await verifierPage.goto(`/verifier/requests/${requestId}`);
    await verifierPage.waitForSelector('[data-testid="presentation-status"]', { timeout: 30000 });
    await expect(verifierPage.locator('[data-testid="presentation-status"]')).toContainText("VERIFIED");

    await verifierContext.close();
  });

  test("should handle selective disclosure", async ({ page, browser }) => {
    // Verifier requests only specific claims
    const verifierContext = await browser.newContext();
    const verifierPage = await verifierContext.newPage();
    const verifierAuth = new AuthHelpers(verifierPage);

    await verifierPage.goto("/");
    await verifierAuth.login(SEEDED_USERS.verifier.email, SEEDED_PASSWORDS.verifier);

    await verifierPage.goto("/verifier/create-request");
    await verifierPage.waitForSelector('[data-testid="presentation-request-form"]');

    // Request only age verification (birth_date for age check)
    await verifierPage.selectOption('[data-testid="requested-credential-type"]', "org.iso.18013.5.1.mDL");
    await verifierPage.check('[data-testid="claim-birth_date"]');
    await verifierPage.selectOption('[data-testid="age-check-mode"]', "OVER_21");

    await verifierPage.click('[data-testid="generate-presentation-qr"]');
    await verifierPage.waitForSelector('[data-testid="presentation-qr-code"]');

    const presentationRequestUri = await verifierPage.getAttribute(
      '[data-testid="presentation-qr-data"]',
      "data-value"
    );

    // Wallet scans and responds
    await walletBridge.init();
    await walletBridge.setDeviceId(deviceId);

    const scanResult = await walletBridge.scanQrCode(presentationRequestUri);
    expect(scanResult.success).toBe(true);
    expect(scanResult.requestedClaims).toEqual(["birth_date"]);

    // Verify only requested claim is disclosed
    const presentationResult = await walletBridge._waitForMessage("PRESENTATION_SUBMITTED", 15000);
    expect(presentationResult.success).toBe(true);
    expect(presentationResult.presentedClaims).toHaveProperty("birth_date");
    expect(presentationResult.presentedClaims).not.toHaveProperty("given_name");
    expect(presentationResult.presentedClaims).not.toHaveProperty("family_name");
    expect(presentationResult.presentedClaims).not.toHaveProperty("document_number");

    await verifierContext.close();
  });

  test("should reject presentation request for missing credential", async ({ page, browser }) => {
    // Create a new wallet without credentials
    const emptyDeviceResult = await deviceHelpers.registerDevice("empty@test.com", {
      platform: "web",
    });

    const verifierContext = await browser.newContext();
    const verifierPage = await verifierContext.newPage();
    const verifierAuth = new AuthHelpers(verifierPage);

    await verifierPage.goto("/");
    await verifierAuth.login(SEEDED_USERS.verifier.email, SEEDED_PASSWORDS.verifier);

    await verifierPage.goto("/verifier/create-request");
    await verifierPage.waitForSelector('[data-testid="presentation-request-form"]');

    // Request a credential type not in wallet
    await verifierPage.selectOption('[data-testid="requested-credential-type"]', "org.iso.18013.5.1.mDL");
    await verifierPage.check('[data-testid="claim-given_name"]');

    await verifierPage.click('[data-testid="generate-presentation-qr"]');
    await verifierPage.waitForSelector('[data-testid="presentation-qr-code"]');

    const presentationRequestUri = await verifierPage.getAttribute(
      '[data-testid="presentation-qr-data"]',
      "data-value"
    );

    // New wallet with no credentials
    const emptyWalletBridge = new WalletBridge(page, process.env.WALLET_URL || "http://localhost:5000");
    await emptyWalletBridge.init();
    await emptyWalletBridge.setDeviceId(emptyDeviceResult.deviceId);

    const scanResult = await emptyWalletBridge.scanQrCode(presentationRequestUri);
    
    // Should indicate no matching credentials
    expect(scanResult.success).toBe(true);
    expect(scanResult.type).toBe("PRESENTATION_REQUEST");
    expect(scanResult.matchingCredentials).toEqual([]);
    expect(scanResult.canFulfill).toBe(false);

    await verifierContext.close();
  });

  test("should handle expired presentation request", async ({ page, browser }) => {
    const verifierContext = await browser.newContext();
    const verifierPage = await verifierContext.newPage();
    const verifierAuth = new AuthHelpers(verifierPage);

    await verifierPage.goto("/");
    await verifierAuth.login(SEEDED_USERS.verifier.email, SEEDED_PASSWORDS.verifier);

    await verifierPage.goto("/verifier/create-request");
    await verifierPage.waitForSelector('[data-testid="presentation-request-form"]');

    // Create request with very short expiry
    await verifierPage.selectOption('[data-testid="requested-credential-type"]', "org.iso.18013.5.1.mDL");
    await verifierPage.check('[data-testid="claim-given_name"]');
    await verifierPage.fill('[data-testid="request-expiry-seconds"]', "1"); // 1 second

    await verifierPage.click('[data-testid="generate-presentation-qr"]');
    await verifierPage.waitForSelector('[data-testid="presentation-qr-code"]');

    const presentationRequestUri = await verifierPage.getAttribute(
      '[data-testid="presentation-qr-data"]',
      "data-value"
    );

    // Wait for request to expire
    await page.waitForTimeout(2000);

    // Try to scan expired request
    await walletBridge.init();
    await walletBridge.setDeviceId(deviceId);

    const scanResult = await walletBridge.scanQrCode(presentationRequestUri);
    expect(scanResult.success).toBe(false);
    expect(scanResult.error).toContain("expired");

    await verifierContext.close();
  });
});
