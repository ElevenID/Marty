/**
 * Full Workflow E2E Test
 *
 * Tests the complete mDoc credential issuance workflow:
 * 1. Issuer logs in and creates an organization
 * 2. Configures organization to issue credentials
 * 3. Invites an applicant to the organization
 * 4. Applicant fills out application
 * 5. Org admin approves the application
 * 6. Issues credential to the applicant's device
 * 7. Device receives credential via push notification
 * 8. Device responds to challenges with RSA signatures
 *
 * This test validates the entire path from org setup to credential issuance.
 *
 * NOTE: These tests require specific data-testid elements and API endpoints
 * that are not yet implemented. Skip until infrastructure is ready.
 */

const { test, expect } = require("@playwright/test");
const {
  AuthHelpers,
  WalletBridge,
  PushNotificationHelpers,
  DeviceRegistrationHelpers,
  MailHogHelpers,
  generateTestEmail,
  SEEDED_USERS,
  SEEDED_PASSWORDS,
} = require("../utils/test-helpers");

// Skip entire test suite - requires organization management UI components (data-testid)
// and backend APIs that are not yet implemented
test.describe.skip("Full Credential Issuance Workflow", () => {
  const ORG_NAME = `Test Org ${Date.now()}`;
  const APPLICANT_EMAIL = generateTestEmail("applicant");
  
  let issuerAuth;
  let applicantAuth;
  let walletBridge;
  let pushHelpers;
  let deviceHelpers;
  let mailHelpers;
  
  // Shared state across tests
  let organizationId;
  let invitationCode;
  let applicationId;
  let credentialId;
  let deviceId;

  test.beforeAll(async ({ browser }) => {
    // Create a context for setup
    const context = await browser.newContext();
    const page = await context.newPage();
    
    deviceHelpers = new DeviceRegistrationHelpers(page);
    pushHelpers = new PushNotificationHelpers(page, deviceHelpers);
    
    await context.close();
  });

  test("1. Issuer creates organization", async ({ page }) => {
    issuerAuth = new AuthHelpers(page);
    
    // Login as issuer/vendor
    await page.goto("/");
    await issuerAuth.login(SEEDED_USERS.vendor.email, SEEDED_PASSWORDS.vendor);
    
    // Navigate to org creation
    await page.click('[data-testid="create-organization"]');
    await page.waitForSelector('[data-testid="org-form"]');
    
    // Fill org details
    await page.fill('[data-testid="org-name"]', ORG_NAME);
    await page.fill('[data-testid="org-description"]', "Test organization for E2E testing");
    await page.selectOption('[data-testid="org-type"]', "ISSUER");
    
    // Submit
    await page.click('[data-testid="submit-org"]');
    await page.waitForSelector('[data-testid="org-created-success"]');
    
    // Get organization ID
    organizationId = await page.getAttribute('[data-testid="org-id"]', "data-value");
    expect(organizationId).toBeTruthy();
    
    console.log(`Created organization: ${organizationId}`);
  });

  test("2. Issuer configures credential issuance", async ({ page }) => {
    issuerAuth = new AuthHelpers(page);
    
    await page.goto("/");
    await issuerAuth.login(SEEDED_USERS.vendor.email, SEEDED_PASSWORDS.vendor);
    
    // Navigate to credential configuration
    await page.goto(`/admin/organizations/${organizationId}/credentials`);
    await page.waitForSelector('[data-testid="credential-config"]');
    
    // Enable mDoc credential type
    await page.click('[data-testid="add-credential-type"]');
    await page.selectOption('[data-testid="credential-format"]', "mDoc");
    await page.selectOption('[data-testid="credential-doctype"]', "org.iso.18013.5.1.mDL");
    
    // Configure required fields
    await page.check('[data-testid="field-given_name"]');
    await page.check('[data-testid="field-family_name"]');
    await page.check('[data-testid="field-birth_date"]');
    await page.check('[data-testid="field-document_number"]');
    
    // Save configuration
    await page.click('[data-testid="save-credential-config"]');
    await page.waitForSelector('[data-testid="config-saved-success"]');
    
    console.log("Credential configuration saved");
  });

  test("3. Issuer invites applicant", async ({ page }) => {
    issuerAuth = new AuthHelpers(page);
    mailHelpers = new MailHogHelpers(page);
    
    await page.goto("/");
    await issuerAuth.login(SEEDED_USERS.vendor.email, SEEDED_PASSWORDS.vendor);
    
    // Navigate to invitations
    await page.goto(`/admin/organizations/${organizationId}/invitations`);
    await page.waitForSelector('[data-testid="invitation-form"]');
    
    // Send invitation
    await page.fill('[data-testid="invitee-email"]', APPLICANT_EMAIL);
    await page.selectOption('[data-testid="invitation-role"]', "APPLICANT");
    await page.click('[data-testid="send-invitation"]');
    
    await page.waitForSelector('[data-testid="invitation-sent-success"]');
    
    // Wait for email to arrive
    const email = await mailHelpers.waitForEmail(APPLICANT_EMAIL, "Invitation", 30000);
    expect(email).toBeTruthy();
    
    // Extract invitation code from email
    const emailBody = email.Content?.Body || email.Raw?.Data;
    const codeMatch = emailBody.match(/code[=:]?\s*([A-Z0-9]{6,})/i);
    invitationCode = codeMatch ? codeMatch[1] : null;
    expect(invitationCode).toBeTruthy();
    
    console.log(`Invitation sent with code: ${invitationCode}`);
  });

  test("4. Applicant registers device with RSA keypair", async ({ page }) => {
    deviceHelpers = new DeviceRegistrationHelpers(page);
    pushHelpers = new PushNotificationHelpers(page, deviceHelpers);
    
    // Register device with RSA keypair for challenge signing
    const result = await deviceHelpers.registerDevice(APPLICANT_EMAIL, {
      platform: "web",
    });
    
    deviceId = result.deviceId;
    expect(deviceId).toBeTruthy();
    expect(result.keypair).toBeTruthy();
    expect(result.keypair.keyId).toBeTruthy();
    
    console.log(`Device registered: ${deviceId} with key ID: ${result.keypair.keyId}`);
  });

  test("5. Applicant accepts invitation and submits application", async ({ page }) => {
    applicantAuth = new AuthHelpers(page);
    
    // Accept invitation via link
    await page.goto(`/invitations/accept?code=${invitationCode}`);
    
    // Register as new applicant (or login if exists)
    await page.waitForSelector('[data-testid="accept-invitation"]');
    await page.fill('[data-testid="register-email"]', APPLICANT_EMAIL);
    await page.fill('[data-testid="register-password"]', "TestPassword123!");
    await page.fill('[data-testid="register-confirm-password"]', "TestPassword123!");
    await page.click('[data-testid="register-submit"]');
    
    await page.waitForSelector('[data-testid="invitation-accepted"]');
    
    // Navigate to application form
    await page.goto(`/organizations/${organizationId}/apply`);
    await page.waitForSelector('[data-testid="application-form"]');
    
    // Fill out application
    await page.fill('[data-testid="given-name"]', "Test");
    await page.fill('[data-testid="family-name"]', "Applicant");
    await page.fill('[data-testid="birth-date"]', "1990-01-15");
    await page.fill('[data-testid="document-number"]', "DL123456789");
    
    // Submit application
    await page.click('[data-testid="submit-application"]');
    await page.waitForSelector('[data-testid="application-submitted"]');
    
    // Get application ID
    applicationId = await page.getAttribute('[data-testid="application-id"]', "data-value");
    expect(applicationId).toBeTruthy();
    
    console.log(`Application submitted: ${applicationId}`);
  });

  test("6. Admin approves application and issues credential", async ({ page }) => {
    issuerAuth = new AuthHelpers(page);
    
    await page.goto("/");
    await issuerAuth.login(SEEDED_USERS.vendor.email, SEEDED_PASSWORDS.vendor);
    
    // Navigate to application review
    await page.goto(`/admin/applications/${applicationId}`);
    await page.waitForSelector('[data-testid="application-details"]');
    
    // Verify applicant details
    await expect(page.locator('[data-testid="applicant-name"]')).toContainText("Test Applicant");
    await expect(page.locator('[data-testid="application-status"]')).toContainText("PENDING");
    
    // Approve application
    await page.click('[data-testid="approve-application"]');
    await page.fill('[data-testid="approval-notes"]', "Application verified and approved");
    await page.click('[data-testid="confirm-approval"]');
    
    await page.waitForSelector('[data-testid="approval-success"]');
    
    // Issue credential
    await page.click('[data-testid="issue-credential"]');
    await page.selectOption('[data-testid="credential-type"]', "org.iso.18013.5.1.mDL");
    await page.fill('[data-testid="validity-days"]', "365");
    await page.click('[data-testid="confirm-issue"]');
    
    await page.waitForSelector('[data-testid="credential-issued"]');
    
    // Get credential ID
    credentialId = await page.getAttribute('[data-testid="credential-id"]', "data-value");
    expect(credentialId).toBeTruthy();
    
    console.log(`Credential issued: ${credentialId}`);
  });

  test("7. Wallet receives credential via push notification", async ({ page }) => {
    walletBridge = new WalletBridge(page, process.env.WALLET_URL || "http://localhost:5000");
    deviceHelpers = new DeviceRegistrationHelpers(page);
    pushHelpers = new PushNotificationHelpers(page, deviceHelpers);
    
    // Initialize wallet bridge
    await walletBridge.init();
    await walletBridge.setDeviceId(deviceId);
    
    // Wait for credential to arrive
    const credentials = await walletBridge.waitForCredentials(30000);
    expect(credentials.length).toBeGreaterThan(0);
    
    const receivedCredential = credentials.find((c) => c.id === credentialId);
    expect(receivedCredential).toBeTruthy();
    expect(receivedCredential.doctype).toBe("org.iso.18013.5.1.mDL");
    
    // Verify credential claims
    expect(receivedCredential.claims.given_name).toBe("Test");
    expect(receivedCredential.claims.family_name).toBe("Applicant");
    
    console.log("Credential received in wallet");
  });

  test("8. Wallet responds to push challenge with RSA signature", async ({ page }) => {
    deviceHelpers = new DeviceRegistrationHelpers(page);
    pushHelpers = new PushNotificationHelpers(page, deviceHelpers);
    
    // Restore keypair from step 4 (in real test, this would be persisted)
    // For now, we'll create a new challenge and respond
    
    // Create a test challenge
    const nonce = `test-nonce-${Date.now()}`;
    const challenge = await pushHelpers.createPushChallenge(deviceId, {
      title: "Verification Request",
      question: "Please confirm your identity",
      nonce,
      credential_id: credentialId,
      ttl_seconds: 120,
    });
    
    expect(challenge.challenge_id).toBeTruthy();
    
    // Respond with auto-signed signature (uses keypair from device registration)
    const result = await pushHelpers.respondToChallenge(
      deviceId,
      challenge.challenge_id,
      "accept",
      nonce
    );
    
    expect(result.success).toBe(true);
    expect(result.response).toBe("accept");
    
    // Verify challenge is no longer pending
    const pending = await pushHelpers.getPendingChallenges(deviceId);
    expect(pending.find((c) => c.challenge_id === challenge.challenge_id)).toBeFalsy();
    
    console.log("Challenge response verified with RSA signature");
  });

  test("9. Verify credential status is active", async ({ page }) => {
    walletBridge = new WalletBridge(page, process.env.WALLET_URL || "http://localhost:5000");
    
    await walletBridge.init();
    await walletBridge.setDeviceId(deviceId);
    
    // Get stored credentials
    const credentials = await walletBridge.getCredentials();
    const credential = credentials.find((c) => c.id === credentialId);
    
    expect(credential).toBeTruthy();
    expect(credential.status).toBe("ACTIVE");
    expect(credential.issuer).toBe(ORG_NAME);
    
    console.log("Full workflow completed successfully!");
  });
});
