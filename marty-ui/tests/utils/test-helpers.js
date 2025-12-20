// Test utilities and helpers
const { expect } = require('@playwright/test');
const crypto = require('crypto');
const { SEEDED_USERS, SEEDED_PASSWORDS, SEEDED_ORGS, getUserByRole } = require('../fixtures/users');

// =============================================================================
// RSA Key Utilities for Push Challenge Signing
// =============================================================================

/**
 * Generate an RSA keypair for testing push challenges.
 * Returns keypair with PEM-encoded keys and DER-encoded public key for API.
 */
function generateTestKeypair() {
  const { publicKey, privateKey } = crypto.generateKeyPairSync('rsa', {
    modulusLength: 2048,
    publicKeyEncoding: { type: 'pkcs1', format: 'pem' },
    privateKeyEncoding: { type: 'pkcs1', format: 'pem' },
  });
  
  // Export public key as DER for API registration
  const publicKeyDer = crypto.createPublicKey(publicKey).export({
    type: 'pkcs1',
    format: 'der',
  });
  
  // Compute key ID as first 16 chars of SHA-256 hex digest (per RFC 7638)
  const keyId = crypto.createHash('sha256').update(publicKeyDer).digest('hex').substring(0, 16);
  
  return {
    publicKeyPem: publicKey,
    privateKeyPem: privateKey,
    publicKeyDerBase64: publicKeyDer.toString('base64'),
    keyId,
  };
}

/**
 * Sign a challenge nonce using RSA PKCS#1 SHA-256.
 * @param {string} privateKeyPem - PEM-encoded private key
 * @param {string} nonce - Challenge nonce to sign
 * @returns {string} Base64-encoded signature
 */
function signChallenge(privateKeyPem, nonce) {
  const sign = crypto.createSign('RSA-SHA256');
  sign.update(nonce);
  sign.end();
  return sign.sign(privateKeyPem, 'base64');
}

class DemoTestHelpers {
  constructor(page) {
    this.page = page;
  }

  // Navigation helpers
  async navigateToTab(tabName) {
    await this.page.click(`text=${tabName}`);
    await this.page.waitForLoadState('networkidle');
  }

  async waitForPageLoad() {
    await this.page.waitForLoadState('domcontentloaded');
    await this.page.waitForLoadState('networkidle');
  }

  // Common UI interaction helpers
  async fillFormField(label, value) {
    await this.page.fill(`[aria-label="${label}"], [placeholder*="${label}"], input[name*="${label.toLowerCase()}"]`, value);
  }

  async clickButton(buttonText) {
    await this.page.click(`button:has-text("${buttonText}")`);
  }

  async waitForAlert(type = 'success') {
    await this.page.waitForSelector(`[role="alert"]:has-text("${type}"), .MuiAlert-${type}`);
  }

  async waitForApiCall(urlPattern) {
    return this.page.waitForResponse(response =>
      response.url().includes(urlPattern) &&
      response.status() === 200
    );
  }

  // Enhanced features helpers
  async selectAgeVerificationUseCase(useCase) {
    await this.page.click('[role="button"]:has-text("Use Case")');
    await this.page.click(`[role="option"]:has-text("${useCase}")`);
  }

  async verifyQRCodeGenerated() {
    await this.page.waitForSelector('img[alt*="QR"], canvas');
    const qrElement = await this.page.locator('img[alt*="QR"], canvas').first();
    await expect(qrElement).toBeVisible();
  }

  async expandAccordion(title) {
    await this.page.click(`[aria-expanded="false"]:has-text("${title}")`);
  }

  async verifyCardContent(cardTitle, expectedContent) {
    const card = this.page.locator('.MuiCard-root').filter({ hasText: cardTitle });
    await expect(card).toContainText(expectedContent);
  }

  // API response validation helpers
  async mockApiResponse(url, response) {
    await this.page.route(url, route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(response)
      });
    });
  }

  async verifyApiCall(urlPattern, expectedPayload = null) {
    const [request] = await Promise.all([
      this.page.waitForRequest(request => request.url().includes(urlPattern)),
      // Trigger action that makes the API call
    ]);

    if (expectedPayload) {
      const payload = request.postDataJSON();
      expect(payload).toMatchObject(expectedPayload);
    }

    return request;
  }

  // Assertion helpers
  async verifySuccessMessage(message) {
    await expect(this.page.locator('.MuiAlert-success')).toContainText(message);
  }

  async verifyErrorMessage(message) {
    await expect(this.page.locator('.MuiAlert-error')).toContainText(message);
  }

  async verifyChipStatus(status, color) {
    const chip = this.page.locator(`.MuiChip-${color}:has-text("${status}")`);
    await expect(chip).toBeVisible();
  }

  async verifyTableRow(rowText) {
    await expect(this.page.locator('tr').filter({ hasText: rowText })).toBeVisible();
  }

  // Screenshot helpers for visual testing
  async takeScreenshot(name) {
    await this.page.screenshot({
      path: `test-results/screenshots/${name}.png`,
      fullPage: true
    });
  }

  async compareScreenshot(name) {
    await expect(this.page).toHaveScreenshot(`${name}.png`);
  }
}

// Mock data for testing
const mockCredentialData = {
  given_name: 'Jane',
  family_name: 'Doe',
  birth_date: '1990-01-01',
  document_number: 'DL123456789',
  issuing_country: 'XX',
  issuing_authority: 'Demo DMV',
  expiry_date: '2030-01-01'
};

const mockVerifiablePresentation = {
  "@context": ["https://www.w3.org/2018/credentials/v1"],
  "type": ["VerifiablePresentation"],
  "verifiableCredential": [{
    "@context": ["https://www.w3.org/2018/credentials/v1"],
    "type": ["VerifiableCredential", "mDL"],
    "issuer": "did:example:issuer",
    "issuanceDate": new Date().toISOString(),
    "credentialSubject": mockCredentialData
  }]
};

const mockApiResponses = {
  issuerSuccess: {
    success: true,
    credential: {
      id: 'cred_123456',
      type: 'mDL',
      format: 'mso_mdoc',
      created_at: new Date().toISOString()
    }
  },

  verifierSuccess: {
    success: true,
    verified: true,
    checks: [
      { check_name: 'Signature Verification', passed: true, details: 'Valid signature' },
      { check_name: 'Certificate Chain', passed: true, details: 'Valid certificate chain' },
      { check_name: 'Expiry Check', passed: true, details: 'Credential not expired' }
    ],
    presentation_summary: {
      holder: 'Jane Doe',
      credential_type: 'mDL',
      attributes_shared: ['given_name', 'family_name', 'age_over_21']
    }
  },

  ageVerificationSuccess: {
    verification_result: {
      verified: true,
      age_requirement_met: true,
      use_case: 'alcohol_purchase'
    },
    privacy_report: {
      privacy_level: 'high',
      attributes_disclosed: ['age_over_21'],
      attributes_protected: ['birth_date', 'exact_age'],
      zero_knowledge_proof_used: true
    }
  },

  offlineQRSuccess: {
    success: true,
    offline_qr: {
      qr_code_data: 'mock_cbor_data',
      qr_code_image: 'iVBORw0KGgoAAAANSUhEUgAAABQAAAAU...', // Mock base64
      size_bytes: 1024,
      expires_at: new Date(Date.now() + 3600000).toISOString()
    }
  },

  certificateDashboard: {
    overview: {
      total_certificates: 5,
      critical_alerts: 1,
      certificates_needing_renewal: 2,
      expired_certificates: 0
    },
    certificates: [
      {
        certificate_id: 'dsc_001',
        common_name: 'Demo DMV DSC',
        status: 'critical',
        days_until_expiry: 7,
        issuer: 'Demo Root CA'
      },
      {
        certificate_id: 'dsc_002',
        common_name: 'Test Authority DSC',
        status: 'expiring_soon',
        days_until_expiry: 25,
        issuer: 'Test Root CA'
      }
    ]
  },

  policyEvaluation: {
    recommended_action: 'approve',
    disclosed_attributes: ['given_name', 'age_over_21'],
    protected_attributes: ['birth_date', 'address', 'document_number'],
    privacy_score: 0.85,
    rationale: 'Commercial context with verified business, minimal data disclosure approved'
  }
};

module.exports = {
  DemoTestHelpers,
  mockCredentialData,
  mockVerifiablePresentation,
  mockApiResponses,
};

// =============================================================================
// Authentication Helpers
// =============================================================================

class AuthHelpers {
  constructor(page) {
    this.page = page;
    this.keycloakUrl = process.env.KEYCLOAK_URL || 'http://localhost:8180';
  }

  /**
   * Login with a seeded user
   * @param {string} userType - 'admin', 'vendor', 'applicant1', 'applicant2', 'applicant3'
   */
  async loginAsSeededUser(userType) {
    const user = SEEDED_USERS[userType];
    if (!user) {
      throw new Error(`Unknown seeded user type: ${userType}`);
    }
    return this.login(user.email, user.password);
  }

  /**
   * Login with email and password via Keycloak
   */
  async login(email, password) {
    // Navigate to login if not already there
    const currentUrl = this.page.url();
    if (!currentUrl.includes('realms') && !currentUrl.includes('/auth/')) {
      // Click login button in app - support multiple button text variations
      // "Sign In to Continue" is the main CTA on the landing page
      await this.page.click('button:has-text("Sign In to Continue"), button:has-text("Login"), button:has-text("Sign In"), a:has-text("Login")');
    }

    // Wait for Keycloak login form (handle both auth/login redirect and direct Keycloak)
    await this.page.waitForSelector('#username, #kc-form-login, input[name="username"]', { timeout: 15000 });

    // Fill and submit
    await this.page.fill('#username', email);
    await this.page.fill('#password', password);
    await this.page.click('#kc-login, button[type="submit"]');

    // Wait for redirect back to app
    await this.page.waitForURL(url => !url.toString().includes('realms'), { timeout: 15000 });
    await this.page.waitForLoadState('networkidle');
  }

  /**
   * Logout from the application
   */
  async logout() {
    await this.page.click('button:has-text("Logout"), button:has-text("Sign Out")');
    await this.page.waitForURL(url => !url.toString().includes('/dashboard'), { timeout: 10000 });
  }

  /**
   * Check if currently authenticated
   */
  async isAuthenticated() {
    try {
      await this.page.waitForTimeout(500);
      const logoutButton = this.page.locator('button:has-text("Logout"), button:has-text("Sign Out")');
      return await logoutButton.isVisible();
    } catch {
      return false;
    }
  }
}

// =============================================================================
// Mobile Wallet Helpers
// =============================================================================

class MobileWalletHelpers {
  constructor(page) {
    this.page = page;
    this.walletFrame = null;
    this.walletUrl = process.env.WALLET_URL || 'http://localhost:9081';
  }

  /**
   * Open the mobile wallet iframe
   * @param {string} deviceId - Optional device ID to inject
   * @param {string} orgId - Optional organization ID
   */
  async openWallet(deviceId = null, orgId = null) {
    // Construct URL with test parameters
    let url = `${this.walletUrl}?test_mode=true`;
    if (deviceId) {
      url += `&device_id=${encodeURIComponent(deviceId)}`;
    }
    if (orgId) {
      url += `&org_id=${encodeURIComponent(orgId)}`;
    }

    // Find or create wallet iframe
    const existingFrame = this.page.frameLocator('#wallet-frame');
    if (await existingFrame.locator('body').count() > 0) {
      this.walletFrame = existingFrame;
      return;
    }

    // Navigate to wallet in new tab for standalone testing
    await this.page.goto(url);
    await this.page.waitForLoadState('networkidle');
  }

  /**
   * Send a message to the wallet via postMessage
   * @param {string} type - Message type
   * @param {object} payload - Message payload
   */
  async sendMessage(type, payload) {
    await this.page.evaluate(({ type, payload, walletUrl }) => {
      const walletFrame = document.getElementById('wallet-frame');
      if (walletFrame && walletFrame.contentWindow) {
        walletFrame.contentWindow.postMessage({ type, payload }, walletUrl);
      }
    }, { type, payload, walletUrl: this.walletUrl });
  }

  /**
   * Inject a QR code payload for the wallet to scan
   * @param {string} qrData - QR code data (credential offer or presentation request)
   */
  async injectQRCode(qrData) {
    await this.sendMessage('SCAN_QR_CODE', { data: qrData });
    await this.page.waitForTimeout(500); // Give Flutter time to process
  }

  /**
   * Wait for wallet to show credential offer
   */
  async waitForCredentialOffer() {
    if (this.walletFrame) {
      await this.walletFrame.locator('text=Credential Offer').waitFor({ timeout: 10000 });
    } else {
      await this.page.waitForSelector('text=Credential Offer', { timeout: 10000 });
    }
  }

  /**
   * Accept a credential offer in the wallet
   */
  async acceptCredentialOffer() {
    const acceptButton = this.walletFrame 
      ? this.walletFrame.locator('button:has-text("Accept"), button:has-text("Add Credential")')
      : this.page.locator('button:has-text("Accept"), button:has-text("Add Credential")');
    await acceptButton.click();
    await this.page.waitForTimeout(1000);
  }

  /**
   * Get the current device ID from the wallet
   */
  async getDeviceId() {
    return await this.page.evaluate(() => {
      // Flutter web stores device ID in localStorage
      return localStorage.getItem('marty_device_id');
    });
  }

  /**
   * Set a test device ID in the wallet
   * @param {string} deviceId - Device ID to set
   */
  async setDeviceId(deviceId) {
    await this.page.evaluate((id) => {
      localStorage.setItem('marty_device_id', id);
    }, deviceId);
  }

  /**
   * Get stored credentials from the wallet
   */
  async getStoredCredentials() {
    return await this.page.evaluate(() => {
      const stored = localStorage.getItem('marty_credentials');
      return stored ? JSON.parse(stored) : [];
    });
  }

  /**
   * Clear all wallet data (for test cleanup)
   */
  async clearWalletData() {
    await this.page.evaluate(() => {
      localStorage.removeItem('marty_device_id');
      localStorage.removeItem('marty_credentials');
      localStorage.removeItem('marty_push_token');
    });
  }
}

// =============================================================================
// WalletBridge - Full postMessage-based wallet control for E2E testing
// =============================================================================

/**
 * WalletBridge provides bidirectional postMessage communication with
 * the Flutter web wallet for E2E testing. It handles message sending,
 * response waiting, and wallet lifecycle events.
 */
class WalletBridge {
  constructor(page) {
    this.page = page;
    this.walletUrl = process.env.WALLET_URL || 'http://localhost:9081';
    this.apiUrl = process.env.API_URL || 'http://localhost:8000';
    this._isReady = false;
    this._messageQueue = [];
    this._responseHandlers = new Map();
  }

  /**
   * Initialize the wallet bridge and wait for wallet to be ready.
   * @param {object} options - Initialization options
   * @param {string} options.deviceId - Optional device ID to inject
   * @param {string} options.orgId - Optional organization ID
   * @param {number} options.timeout - Timeout for wallet ready (ms)
   */
  async init(options = {}) {
    const { deviceId, orgId, timeout = 30000 } = options;

    // Construct URL with test parameters
    let url = `${this.walletUrl}?test_mode=true&api_url=${encodeURIComponent(this.apiUrl)}`;
    if (deviceId) url += `&device_id=${encodeURIComponent(deviceId)}`;
    if (orgId) url += `&org_id=${encodeURIComponent(orgId)}`;

    // Set up message listener before navigating
    await this._setupMessageListener();

    // Navigate to wallet
    await this.page.goto(url);

    // Wait for WALLET_READY message
    await this._waitForMessage('WALLET_READY', timeout);
    this._isReady = true;

    console.log('WalletBridge: Wallet ready');
    return true;
  }

  /**
   * Set up postMessage listener in the page context
   */
  async _setupMessageListener() {
    await this.page.exposeFunction('_walletBridgeReceive', (data) => {
      const { type, payload } = data;
      
      // Resolve any waiting promises for this message type
      if (this._responseHandlers.has(type)) {
        const handlers = this._responseHandlers.get(type);
        handlers.forEach(resolve => resolve(payload));
        this._responseHandlers.delete(type);
      }

      // Store in queue for later inspection
      this._messageQueue.push({ type, payload, timestamp: Date.now() });
    });

    await this.page.evaluate(() => {
      window.addEventListener('message', (event) => {
        if (event.data?.source === 'marty-wallet') {
          window._walletBridgeReceive(event.data);
        }
      });
    });
  }

  /**
   * Wait for a specific message type from the wallet
   */
  async _waitForMessage(type, timeout = 10000) {
    return new Promise((resolve, reject) => {
      const timeoutId = setTimeout(() => {
        reject(new Error(`Timeout waiting for message: ${type}`));
      }, timeout);

      if (!this._responseHandlers.has(type)) {
        this._responseHandlers.set(type, []);
      }
      this._responseHandlers.get(type).push((payload) => {
        clearTimeout(timeoutId);
        resolve(payload);
      });
    });
  }

  /**
   * Send a message to the wallet and optionally wait for response
   */
  async sendMessage(type, payload = {}, waitForResponse = null) {
    await this.page.evaluate(({ type, payload }) => {
      window.postMessage({ type, payload }, '*');
    }, { type, payload });

    if (waitForResponse) {
      return this._waitForMessage(waitForResponse);
    }
  }

  /**
   * Inject a QR code (credential offer or presentation request) into the wallet
   * @param {string} qrData - QR code data (URL or encoded data)
   */
  async scanQrCode(qrData) {
    return this.sendMessage('SCAN_QR_CODE', { data: qrData }, 'QR_CODE_INJECTED');
  }

  /**
   * Inject a push challenge into the wallet for testing
   * @param {object} challenge - Challenge data
   */
  async injectChallenge(challenge) {
    return this.sendMessage('INJECT_CHALLENGE', challenge, 'CHALLENGE_INJECTED');
  }

  /**
   * Set the device ID in the wallet
   * @param {string} deviceId - Device ID
   * @param {string} orgId - Optional organization ID
   */
  async setDeviceId(deviceId, orgId = null) {
    return this.sendMessage('SET_DEVICE_ID', { device_id: deviceId, org_id: orgId }, 'DEVICE_ID_SET');
  }

  /**
   * Get the current device ID from the wallet
   */
  async getDeviceId() {
    const response = await this.sendMessage('GET_DEVICE_ID', {}, 'DEVICE_ID');
    return response?.device_id;
  }

  /**
   * Get stored credentials from the wallet
   */
  async getCredentials() {
    const response = await this.sendMessage('GET_CREDENTIALS', {}, 'CREDENTIALS');
    return response?.credentials || [];
  }

  /**
   * Clear all wallet data (for test cleanup)
   */
  async clearData() {
    return this.sendMessage('CLEAR_DATA', {}, 'DATA_CLEARED');
  }

  /**
   * Wait for the wallet to have at least N credentials
   * @param {number} count - Expected credential count
   * @param {number} timeout - Timeout in ms
   */
  async waitForCredentials(count = 1, timeout = 30000) {
    const startTime = Date.now();
    while (Date.now() - startTime < timeout) {
      const credentials = await this.getCredentials();
      if (credentials.length >= count) {
        return credentials;
      }
      await this.page.waitForTimeout(500);
    }
    throw new Error(`Timeout waiting for ${count} credentials`);
  }

  /**
   * Get all received messages
   */
  getMessageHistory() {
    return [...this._messageQueue];
  }

  /**
   * Clear message history
   */
  clearMessageHistory() {
    this._messageQueue = [];
  }

  /**
   * Check if wallet is ready
   */
  get isReady() {
    return this._isReady;
  }

  // ===========================================================================
  // OID4VP Presentation Request Methods
  // ===========================================================================

  /**
   * Store a credential in the wallet's localStorage
   * @param {object} credential - Credential object with jwt, type, claims, etc.
   */
  async storeCredential(credential) {
    return this.sendMessage('STORE_CREDENTIAL', { credential }, 'CREDENTIAL_STORED');
  }

  /**
   * Process an OID4VP presentation request
   * Sends the request to the wallet which finds matching credentials
   * @param {string} requestUri - The OID4VP request URI
   * @param {string} credentialType - The type of credential being requested
   * @returns {Promise<object>} - Object with matching_credentials array
   */
  async processOid4vpRequest(requestUri, credentialType = null) {
    return this.sendMessage(
      'PROCESS_OID4VP_REQUEST',
      { request_uri: requestUri, credential_type: credentialType },
      'OID4VP_PROCESSED'
    );
  }

  /**
   * Approve a presentation request and create a Verifiable Presentation
   * Uses WASM for real crypto if available, otherwise creates mock VP
   * @param {object} options - Approval options
   * @param {number} options.credentialIndex - Index of credential to use (default: 0)
   * @param {string} options.audience - Verifier audience (default: 'demo_verifier')
   * @param {string} options.nonce - Challenge nonce for replay protection
   * @param {string} options.callbackUrl - URL to submit the presentation to
   * @returns {Promise<object>} - Object with vp_jwt
   */
  async approvePresentation(options = {}) {
    const { credentialIndex = 0, audience = 'demo_verifier', nonce = null, callbackUrl = null } = options;
    return this.sendMessage(
      'APPROVE_PRESENTATION',
      { credential_index: credentialIndex, audience, nonce, callback_url: callbackUrl },
      'PRESENTATION_APPROVED'
    );
  }

  /**
   * Wait for a presentation to be submitted to the verifier
   * Polls the verifier API for the presentation submission
   * @param {string} requestId - The presentation request ID
   * @param {number} timeout - Timeout in ms
   * @returns {Promise<object>} - The submitted presentation data
   */
  async waitForPresentationSubmission(requestId, timeout = 30000) {
    const startTime = Date.now();
    while (Date.now() - startTime < timeout) {
      try {
        const response = await this.page.request.get(
          `${this.apiUrl}/api/test/request-presentation/${requestId}/status`
        );
        if (response.ok()) {
          const data = await response.json();
          if (data.status === 'submitted') {
            return data;
          }
        }
      } catch (err) {
        // Continue polling
      }
      await this.page.waitForTimeout(500);
    }
    throw new Error(`Timeout waiting for presentation submission for request ${requestId}`);
  }

  /**
   * Complete OID4VP flow: process request, approve with first matching credential
   * This is a convenience method for E2E tests
   * @param {string} requestUri - The OID4VP request URI
   * @param {string} credentialType - The type of credential being requested
   * @param {object} options - Additional options for approval
   * @returns {Promise<object>} - Object with vp_jwt and matching credential info
   */
  async completeOid4vpFlow(requestUri, credentialType = null, options = {}) {
    // Process the request to find matching credentials
    const processResult = await this.processOid4vpRequest(requestUri, credentialType);
    
    if (!processResult.success) {
      throw new Error(`Failed to process OID4VP request: ${processResult.error}`);
    }

    if (processResult.matching_count === 0) {
      throw new Error('No matching credentials found for presentation request');
    }

    // Approve with the first matching credential (or specified index)
    const approvalResult = await this.approvePresentation({
      credentialIndex: options.credentialIndex || 0,
      audience: options.audience,
      nonce: options.nonce,
      callbackUrl: options.callbackUrl,
    });

    if (!approvalResult.success) {
      throw new Error(`Failed to approve presentation: ${approvalResult.error}`);
    }

    return {
      ...approvalResult,
      matching_credentials: processResult.matching_credentials,
    };
  }
}

// =============================================================================
// Push Notification Helpers
// =============================================================================

class PushNotificationHelpers {
  constructor(page, deviceRegHelpers = null, userId = null) {
    this.page = page;
    this.apiUrl = process.env.API_URL || 'http://localhost:8000';
    // Optional reference to DeviceRegistrationHelpers for auto-signing
    this.deviceRegHelpers = deviceRegHelpers;
    // User ID for API calls
    this.userId = userId;
  }

  /**
   * Set the user ID for API calls
   * @param {string} userId
   */
  setUserId(userId) {
    this.userId = userId;
  }

  /**
   * Set the DeviceRegistrationHelpers for auto-signing challenges.
   * @param {DeviceRegistrationHelpers} helpers
   */
  setDeviceRegHelpers(helpers) {
    this.deviceRegHelpers = helpers;
  }

  /**
   * Get all mock notifications sent during test
   * @param {number} limit - Max notifications to retrieve
   */
  async getAllNotifications(limit = 50) {
    const response = await this.page.request.get(
      `${this.apiUrl}/api/test/notifications?limit=${limit}`
    );
    const data = await response.json();
    return data.notifications || [];
  }

  /**
   * Get notifications by event type
   * @param {string} eventType - Event type to filter by
   */
  async getNotificationsByEventType(eventType) {
    const response = await this.page.request.get(
      `${this.apiUrl}/api/test/notifications?event_type=${encodeURIComponent(eventType)}`
    );
    const data = await response.json();
    return data.notifications || [];
  }

  /**
   * Create a push challenge for testing
   * @param {string} deviceId - Target device ID
   * @param {object} challenge - Challenge data
   */
  async createPushChallenge(deviceId, challenge) {
    const headers = {};
    if (this.userId) {
      headers['X-User-ID'] = this.userId;
    }
    const response = await this.page.request.post(
      `${this.apiUrl}/api/push/challenges`,
      { 
        data: { device_id: deviceId, ...challenge },
        headers,
      }
    );
    return response.json();
  }

  /**
   * Get pending challenges for a device
   * @param {string} deviceId - Device ID
   */
  async getPendingChallenges(deviceId) {
    const headers = {};
    if (this.userId) {
      headers['X-User-ID'] = this.userId;
    }
    const response = await this.page.request.get(
      `${this.apiUrl}/api/push/challenges/pending?device_id=${encodeURIComponent(deviceId)}`,
      { headers }
    );
    const data = await response.json();
    return data.challenges || [];
  }

  /**
   * Respond to a push challenge with automatic signature generation.
   * If deviceRegHelpers is set and no signature provided, will auto-sign.
   * @param {string} deviceId - Device ID
   * @param {string} challengeId - Challenge ID
   * @param {string} responseValue - 'accept' or 'reject'
   * @param {string} nonce - Challenge nonce (required for auto-signing)
   * @param {string} signature - Optional signature (if not provided, will auto-sign)
   */
  async respondToChallenge(deviceId, challengeId, responseValue, nonce = null, signature = null) {
    // Auto-sign if possible and no signature provided
    if (!signature && nonce && this.deviceRegHelpers) {
      signature = this.deviceRegHelpers.signChallengeForDevice(deviceId, nonce);
    }
    
    const headers = {};
    if (this.userId) {
      headers['X-User-ID'] = this.userId;
    }
    
    const response = await this.page.request.post(
      `${this.apiUrl}/api/push/challenges/${challengeId}/respond?device_id=${encodeURIComponent(deviceId)}`,
      { data: { response: responseValue, signature }, headers }
    );
    return response.json();
  }

  /**
   * Clear all mock notifications (test cleanup)
   */
  async clearAllNotifications() {
    await this.page.request.delete(`${this.apiUrl}/api/test/notifications`);
  }

  /**
   * Clear all push challenges (test cleanup)
   * @param {string} deviceId - Optional device ID, clears all if not specified
   */
  async clearAllChallenges(deviceId = null) {
    const url = deviceId 
      ? `${this.apiUrl}/api/push/challenges?device_id=${encodeURIComponent(deviceId)}`
      : `${this.apiUrl}/api/push/challenges`;
    const headers = {};
    if (this.userId) {
      headers['X-User-ID'] = this.userId;
    }
    await this.page.request.delete(url, { headers });
  }

  /**
   * Wait for a notification with specific event type
   * @param {string} eventType - Event type to wait for
   * @param {number} timeout - Timeout in ms
   */
  async waitForNotification(eventType, timeout = 10000) {
    const startTime = Date.now();
    while (Date.now() - startTime < timeout) {
      const notifications = await this.getNotificationsByEventType(eventType);
      if (notifications.length > 0) {
        return notifications[0];
      }
      await this.page.waitForTimeout(500);
    }
    throw new Error(`Timeout waiting for notification with event type: ${eventType}`);
  }
}

// =============================================================================
// Device Registration Helpers
// =============================================================================

class DeviceRegistrationHelpers {
  constructor(page) {
    this.page = page;
    this.apiUrl = process.env.API_URL || 'http://localhost:8000';
    // Store keypairs by device ID for signing challenges
    this.deviceKeypairs = new Map();
  }

  /**
   * Generate a test device ID
   * @param {string} orgId - Organization ID
   * @param {string} platform - 'ios', 'android', or 'web'
   */
  generateDeviceId(orgId = null, platform = 'web') {
    const platformId = `test-${platform}-${Date.now()}-${Math.random().toString(36).substring(2, 8)}`;
    return orgId ? `${orgId}:${platformId}` : platformId;
  }

  /**
   * Generate a mock FCM token
   */
  generateMockFcmToken() {
    return `mock-fcm-token-${Date.now()}-${Math.random().toString(36).substring(2, 16)}`;
  }

  /**
   * Register a test device with RSA keypair for push challenge signing.
   * @param {string} userId - User ID (for header)
   * @param {object} deviceInfo - Device information
   * @param {boolean} generateKeys - Whether to generate RSA keypair (default true)
   * @returns {object} Response with keypair info if generated
   */
  async registerDevice(userId, deviceInfo, generateKeys = true) {
    const deviceId = deviceInfo.deviceId || this.generateDeviceId();
    let keypair = null;
    let publicKeyDerBase64 = null;
    
    if (generateKeys) {
      keypair = generateTestKeypair();
      publicKeyDerBase64 = keypair.publicKeyDerBase64;
      this.deviceKeypairs.set(deviceId, keypair);
    }
    
    const response = await this.page.request.post(
      `${this.apiUrl}/api/devices/register`,
      {
        headers: { 'X-User-ID': userId },
        data: {
          device_id: deviceId,
          fcm_token: deviceInfo.fcmToken || this.generateMockFcmToken(),
          platform: deviceInfo.platform || 'web',
          app_version: deviceInfo.appVersion || '1.0.0-test',
          os_version: deviceInfo.osVersion,
          device_model: deviceInfo.deviceModel,
          public_key: publicKeyDerBase64,
        },
      }
    );
    
    const result = await response.json();
    
    // Include keypair info in response for tests that need it
    if (keypair) {
      result.keypair = keypair;
    }
    result.deviceId = deviceId;
    
    return result;
  }

  /**
   * Get the keypair for a registered device.
   * @param {string} deviceId - Device ID
   * @returns {object|null} Keypair or null if not found
   */
  getDeviceKeypair(deviceId) {
    return this.deviceKeypairs.get(deviceId) || null;
  }

  /**
   * Sign a challenge nonce for a device.
   * @param {string} deviceId - Device ID
   * @param {string} nonce - Challenge nonce to sign
   * @returns {string|null} Base64-encoded signature or null if no keypair
   */
  signChallengeForDevice(deviceId, nonce) {
    const keypair = this.deviceKeypairs.get(deviceId);
    if (!keypair) {
      return null;
    }
    return signChallenge(keypair.privateKeyPem, nonce);
  }

  /**
   * Unregister a device
   * @param {string} userId - User ID
   * @param {string} deviceId - Device ID to unregister
   */
  async unregisterDevice(userId, deviceId) {
    // Clean up keypair
    this.deviceKeypairs.delete(deviceId);
    
    const response = await this.page.request.delete(
      `${this.apiUrl}/api/devices/${encodeURIComponent(deviceId)}`,
      { headers: { 'X-User-ID': userId } }
    );
    return response.ok();
  }

  /**
   * Get all devices for a user
   * @param {string} userId - User ID
   * @param {string} orgId - Optional organization filter
   */
  async getUserDevices(userId, orgId = null) {
    let url = `${this.apiUrl}/api/devices`;
    if (orgId) {
      url += `?organization_id=${encodeURIComponent(orgId)}`;
    }
    const response = await this.page.request.get(url, {
      headers: { 'X-User-ID': userId },
    });
    const data = await response.json();
    return data.devices || [];
  }
}

// =============================================================================
// MailHog Helpers (for email verification in tests)
// =============================================================================

class MailHogHelpers {
  constructor(page) {
    this.page = page;
    this.mailhogUrl = process.env.MAILHOG_URL || 'http://localhost:8025';
  }

  /**
   * Get all emails from MailHog
   */
  async getAllEmails() {
    const response = await this.page.request.get(`${this.mailhogUrl}/api/v2/messages`);
    const data = await response.json();
    return data.items || [];
  }

  /**
   * Get emails sent to a specific address
   * @param {string} email - Recipient email address
   */
  async getEmailsTo(email) {
    const allEmails = await this.getAllEmails();
    return allEmails.filter(msg => 
      msg.Raw.To?.some(to => to.includes(email)) ||
      msg.Content?.Headers?.To?.some(to => to.includes(email))
    );
  }

  /**
   * Wait for an email to arrive
   * @param {string} email - Recipient email
   * @param {string} subjectContains - Subject must contain this text
   * @param {number} timeout - Timeout in ms
   */
  async waitForEmail(email, subjectContains = null, timeout = 30000) {
    const startTime = Date.now();
    while (Date.now() - startTime < timeout) {
      const emails = await this.getEmailsTo(email);
      for (const msg of emails) {
        const subject = msg.Content?.Headers?.Subject?.[0] || '';
        if (!subjectContains || subject.includes(subjectContains)) {
          return msg;
        }
      }
      await this.page.waitForTimeout(1000);
    }
    throw new Error(`Timeout waiting for email to ${email}`);
  }

  /**
   * Extract link from email body
   * @param {object} email - Email message from MailHog
   * @param {RegExp} pattern - Regex pattern to match link
   */
  extractLink(email, pattern = /https?:\/\/[^\s"<>]+/g) {
    const body = email.Content?.Body || '';
    const matches = body.match(pattern);
    return matches ? matches[0] : null;
  }

  /**
   * Clear all emails
   */
  async clearAllEmails() {
    await this.page.request.delete(`${this.mailhogUrl}/api/v1/messages`);
  }
}

// =============================================================================
// Mock Email Helpers (for CI/CD environments without MailHog)
// =============================================================================

class MockEmailHelpers {
  constructor(page) {
    this.page = page;
    // In-memory email storage keyed by recipient email
    this.emails = new Map();
  }

  /**
   * Get all emails from mock storage
   */
  async getAllEmails() {
    const allEmails = [];
    for (const emails of this.emails.values()) {
      allEmails.push(...emails);
    }
    return allEmails.sort((a, b) => 
      new Date(b.Created) - new Date(a.Created)
    );
  }

  /**
   * Get emails sent to a specific address
   * @param {string} email - Recipient email address
   */
  async getEmailsTo(email) {
    return this.emails.get(email) || [];
  }

  /**
   * Wait for an email to arrive
   * @param {string} email - Recipient email
   * @param {string} subjectContains - Subject must contain this text
   * @param {number} timeout - Timeout in ms
   */
  async waitForEmail(email, subjectContains = null, timeout = 30000) {
    const startTime = Date.now();
    while (Date.now() - startTime < timeout) {
      const emails = await this.getEmailsTo(email);
      for (const msg of emails) {
        const subject = msg.Content?.Headers?.Subject?.[0] || '';
        if (!subjectContains || subject.includes(subjectContains)) {
          return msg;
        }
      }
      await this.page.waitForTimeout(1000);
    }
    throw new Error(`Timeout waiting for email to ${email}`);
  }

  /**
   * Extract link from email body
   * @param {object} email - Email message
   * @param {RegExp} pattern - Regex pattern to match link
   */
  extractLink(email, pattern = /https?:\/\/[^\s"<>]+/g) {
    const body = email.Content?.Body || '';
    const matches = body.match(pattern);
    return matches ? matches[0] : null;
  }

  /**
   * Clear all emails from mock storage
   */
  async clearAllEmails() {
    this.emails.clear();
  }

  /**
   * Mock sending an email (for testing email sending functionality)
   * @param {string} to - Recipient email
   * @param {string} subject - Email subject
   * @param {string} body - Email body (HTML or plain text)
   * @param {string} from - Sender email
   */
  async mockSendEmail(to, subject, body, from = 'noreply@marty.demo') {
    const email = {
      ID: `mock-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      Created: new Date().toISOString(),
      Raw: {
        From: from,
        To: [to],
        Data: `From: ${from}\r\nTo: ${to}\r\nSubject: ${subject}\r\n\r\n${body}`
      },
      Content: {
        Headers: {
          Subject: [subject],
          From: [from],
          To: [to],
          Date: [new Date().toUTCString()],
          'Content-Type': ['text/html; charset=UTF-8']
        },
        Body: body,
        Size: body.length,
        MIME: null
      }
    };

    if (!this.emails.has(to)) {
      this.emails.set(to, []);
    }
    this.emails.get(to).push(email);
    return email;
  }
}

// =============================================================================
// Email Test Helpers (Production-Ready Facade)
// =============================================================================

/**
 * EmailTestHelpers - High-level email testing facade with provider abstraction
 * 
 * This class provides a production-ready email testing interface that automatically
 * selects the appropriate email provider based on the TEST_PROVIDER environment variable:
 * - 'mailhog' (default): Uses MailHog for local development and full E2E testing
 * - 'mock': Uses in-memory mock for CI/CD environments without external dependencies
 * 
 * Usage Examples:
 * 
 * // Basic usage (auto-detects provider)
 * const emailHelper = new EmailTestHelpers(page);
 * await emailHelper.clearAllEmails();
 * const email = await emailHelper.waitForEmail('user@example.com', 'Welcome');
 * 
 * // Content extraction
 * const subject = emailHelper.getEmailSubject(email);
 * const body = emailHelper.getEmailBody(email);
 * const htmlBody = emailHelper.getHtmlBody(email);
 * const links = emailHelper.getAllLinks(email);
 * 
 * // Verification
 * emailHelper.verifyEmailSubject(email, 'Welcome to Marty');
 * emailHelper.verifyEmailContains(email, 'Click here to verify');
 * const hasLink = emailHelper.verifyLinkExists(email, /verify-email/);
 * 
 * // Advanced search
 * const invites = await emailHelper.getEmailsBySubject('Invitation');
 * const latest = await emailHelper.getLatestEmailTo('user@example.com');
 * const adminEmails = await emailHelper.getEmailsFrom('admin@marty.demo');
 */
class EmailTestHelpers {
  constructor(page) {
    this.page = page;
    this.provider = process.env.TEST_PROVIDER || 'mailhog';
    
    // Initialize appropriate low-level helper based on provider
    if (this.provider === 'mock') {
      this.impl = new MockEmailHelpers(page);
    } else {
      this.impl = new MailHogHelpers(page);
    }
  }

  // =============================================================================
  // Delegated Methods (pass-through to underlying provider)
  // =============================================================================

  /**
   * Get all emails
   * @returns {Promise<Array>} Array of email objects
   */
  async getAllEmails() {
    return this.impl.getAllEmails();
  }

  /**
   * Get emails sent to a specific address
   * @param {string} email - Recipient email address
   * @returns {Promise<Array>} Array of email objects
   */
  async getEmailsTo(email) {
    return this.impl.getEmailsTo(email);
  }

  /**
   * Wait for an email to arrive
   * @param {string} email - Recipient email
   * @param {string} subjectContains - Subject must contain this text
   * @param {number} timeout - Timeout in ms
   * @returns {Promise<object>} Email object
   */
  async waitForEmail(email, subjectContains = null, timeout = 30000) {
    return this.impl.waitForEmail(email, subjectContains, timeout);
  }

  /**
   * Extract link from email body
   * @param {object} email - Email message
   * @param {RegExp} pattern - Regex pattern to match link
   * @returns {string|null} Extracted link or null
   */
  extractLink(email, pattern = /https?:\/\/[^\s"<>]+/g) {
    return this.impl.extractLink(email, pattern);
  }

  /**
   * Clear all emails
   */
  async clearAllEmails() {
    return this.impl.clearAllEmails();
  }

  // =============================================================================
  // Content Extraction Methods
  // =============================================================================

  /**
   * Get email subject
   * @param {object} email - Email message
   * @returns {string} Email subject
   */
  getEmailSubject(email) {
    return email.Content?.Headers?.Subject?.[0] || '';
  }

  /**
   * Get email body (HTML or plain text)
   * @param {object} email - Email message
   * @returns {object} Object with html and text properties
   */
  getEmailBody(email) {
    const body = email.Content?.Body || '';
    const contentType = email.Content?.Headers?.['Content-Type']?.[0] || '';
    
    if (contentType.includes('text/html')) {
      return { html: body, text: this._stripHtml(body) };
    } else {
      return { html: null, text: body };
    }
  }

  /**
   * Get HTML body part
   * @param {object} email - Email message
   * @returns {string|null} HTML body or null
   */
  getHtmlBody(email) {
    return this.getEmailBody(email).html;
  }

  /**
   * Get plain text body part
   * @param {object} email - Email message
   * @returns {string} Plain text body
   */
  getTextBody(email) {
    return this.getEmailBody(email).text;
  }

  /**
   * Get all links from email body
   * @param {object} email - Email message
   * @returns {Array<string>} Array of URLs
   */
  getAllLinks(email) {
    const body = email.Content?.Body || '';
    const matches = body.match(/https?:\/\/[^\s"<>]+/g);
    return matches || [];
  }

  /**
   * Extract links by anchor text (works with HTML emails)
   * @param {object} email - Email message
   * @param {string} linkText - Text to search for in anchor tags
   * @returns {string|null} First matching link or null
   */
  extractLinksByText(email, linkText) {
    const htmlBody = this.getHtmlBody(email);
    if (!htmlBody) return null;

    // Match <a> tags with the specified text
    const regex = new RegExp(`<a[^>]+href=["']([^"']+)["'][^>]*>${linkText}</a>`, 'i');
    const match = htmlBody.match(regex);
    return match ? match[1] : null;
  }

  /**
   * Extract action button link (common pattern in email templates)
   * @param {object} email - Email message
   * @returns {string|null} Button link or null
   */
  extractActionButtonLink(email) {
    const htmlBody = this.getHtmlBody(email);
    if (!htmlBody) return null;

    // Match common button patterns
    const patterns = [
      /<a[^>]+class=["'][^"']*button[^"']*["'][^>]+href=["']([^"']+)["']/i,
      /<a[^>]+href=["']([^"']+)["'][^>]+class=["'][^"']*button[^"']*["']/i,
      /<button[^>]+onclick=["'](?:window\.)?location\.href=["']([^"']+)["']/i
    ];

    for (const pattern of patterns) {
      const match = htmlBody.match(pattern);
      if (match) return match[1];
    }

    return null;
  }

  /**
   * Get sender information
   * @param {object} email - Email message
   * @returns {object} Object with email and name properties
   */
  getSenderInfo(email) {
    const from = email.Content?.Headers?.From?.[0] || email.Raw?.From || '';
    const match = from.match(/([^<]+)<([^>]+)>/);
    
    if (match) {
      return { name: match[1].trim(), email: match[2].trim() };
    }
    return { name: '', email: from.trim() };
  }

  /**
   * Get all recipient addresses
   * @param {object} email - Email message
   * @returns {Array<string>} Array of recipient email addresses
   */
  getRecipients(email) {
    const to = email.Content?.Headers?.To || email.Raw?.To || [];
    return Array.isArray(to) ? to : [to];
  }

  // =============================================================================
  // Advanced Search Methods
  // =============================================================================

  /**
   * Get emails by subject (partial match)
   * @param {string} subject - Subject text to search for
   * @returns {Promise<Array>} Array of matching email objects
   */
  async getEmailsBySubject(subject) {
    const allEmails = await this.getAllEmails();
    return allEmails.filter(email => 
      this.getEmailSubject(email).toLowerCase().includes(subject.toLowerCase())
    );
  }

  /**
   * Get emails from a specific sender
   * @param {string} from - Sender email address
   * @returns {Promise<Array>} Array of matching email objects
   */
  async getEmailsFrom(from) {
    const allEmails = await this.getAllEmails();
    return allEmails.filter(email => {
      const sender = this.getSenderInfo(email).email;
      return sender.toLowerCase().includes(from.toLowerCase());
    });
  }

  /**
   * Get latest email to a recipient
   * @param {string} email - Recipient email address
   * @returns {Promise<object|null>} Latest email or null
   */
  async getLatestEmailTo(email) {
    const emails = await this.getEmailsTo(email);
    return emails.length > 0 ? emails[0] : null;
  }

  /**
   * Get email by ID
   * @param {string} id - Email ID
   * @returns {Promise<object|null>} Email object or null
   */
  async getEmailById(id) {
    const allEmails = await this.getAllEmails();
    return allEmails.find(email => email.ID === id) || null;
  }

  /**
   * Count emails to a recipient
   * @param {string} email - Recipient email address
   * @returns {Promise<number>} Count of emails
   */
  async countEmailsTo(email) {
    const emails = await this.getEmailsTo(email);
    return emails.length;
  }

  // =============================================================================
  // Verification Methods (throw on failure)
  // =============================================================================

  /**
   * Verify email subject matches expected value
   * @param {object} email - Email message
   * @param {string} expected - Expected subject (partial match)
   * @throws {Error} If subject doesn't match
   */
  verifyEmailSubject(email, expected) {
    const subject = this.getEmailSubject(email);
    if (!subject.includes(expected)) {
      throw new Error(`Email subject "${subject}" does not contain "${expected}"`);
    }
  }

  /**
   * Verify email body contains text
   * @param {object} email - Email message
   * @param {string} text - Text to search for
   * @throws {Error} If text not found
   */
  verifyEmailContains(email, text) {
    const body = this.getTextBody(email);
    if (!body.includes(text)) {
      throw new Error(`Email body does not contain "${text}"`);
    }
  }

  /**
   * Verify email sender
   * @param {object} email - Email message
   * @param {string} expectedFrom - Expected sender email
   * @throws {Error} If sender doesn't match
   */
  verifyEmailFrom(email, expectedFrom) {
    const sender = this.getSenderInfo(email).email;
    if (!sender.toLowerCase().includes(expectedFrom.toLowerCase())) {
      throw new Error(`Email from "${sender}" does not match expected "${expectedFrom}"`);
    }
  }

  /**
   * Verify email recipient
   * @param {object} email - Email message
   * @param {string} expectedTo - Expected recipient email
   * @throws {Error} If recipient doesn't match
   */
  verifyEmailTo(email, expectedTo) {
    const recipients = this.getRecipients(email);
    const found = recipients.some(to => 
      to.toLowerCase().includes(expectedTo.toLowerCase())
    );
    if (!found) {
      throw new Error(`Email recipients ${recipients.join(', ')} do not include "${expectedTo}"`);
    }
  }

  /**
   * Verify email contains a link matching pattern
   * @param {object} email - Email message
   * @param {RegExp|string} pattern - Pattern to match
   * @returns {boolean} True if link found
   */
  verifyLinkExists(email, pattern) {
    const links = this.getAllLinks(email);
    const regex = pattern instanceof RegExp ? pattern : new RegExp(pattern);
    return links.some(link => regex.test(link));
  }

  /**
   * Verify custom header value
   * @param {object} email - Email message
   * @param {string} headerName - Header name
   * @param {string} expectedValue - Expected header value
   * @throws {Error} If header doesn't match
   */
  verifyHeader(email, headerName, expectedValue) {
    const headerValue = email.Content?.Headers?.[headerName]?.[0] || '';
    if (headerValue !== expectedValue) {
      throw new Error(`Header "${headerName}" value "${headerValue}" does not match "${expectedValue}"`);
    }
  }

  // =============================================================================
  // Waiting Utilities
  // =============================================================================

  /**
   * Wait for specific number of emails to arrive
   * @param {string} email - Recipient email address
   * @param {number} count - Expected number of emails
   * @param {number} timeout - Timeout in ms
   * @returns {Promise<Array>} Array of email objects
   */
  async waitForEmails(email, count, timeout = 30000) {
    const startTime = Date.now();
    while (Date.now() - startTime < timeout) {
      const emails = await this.getEmailsTo(email);
      if (emails.length >= count) {
        return emails.slice(0, count);
      }
      await this.page.waitForTimeout(1000);
    }
    throw new Error(`Timeout waiting for ${count} emails to ${email}`);
  }

  /**
   * Wait for email from specific sender
   * @param {string} recipient - Recipient email address
   * @param {string} from - Sender email address
   * @param {number} timeout - Timeout in ms
   * @returns {Promise<object>} Email object
   */
  async waitForEmailFrom(recipient, from, timeout = 30000) {
    const startTime = Date.now();
    while (Date.now() - startTime < timeout) {
      const emails = await this.getEmailsTo(recipient);
      for (const email of emails) {
        const sender = this.getSenderInfo(email).email;
        if (sender.toLowerCase().includes(from.toLowerCase())) {
          return email;
        }
      }
      await this.page.waitForTimeout(1000);
    }
    throw new Error(`Timeout waiting for email from ${from} to ${recipient}`);
  }

  /**
   * Wait for email containing specific link
   * @param {string} email - Recipient email address
   * @param {RegExp|string} linkPattern - Link pattern to match
   * @param {number} timeout - Timeout in ms
   * @returns {Promise<object>} Email object
   */
  async waitForEmailWithLink(email, linkPattern, timeout = 30000) {
    const startTime = Date.now();
    const regex = linkPattern instanceof RegExp ? linkPattern : new RegExp(linkPattern);
    
    while (Date.now() - startTime < timeout) {
      const emails = await this.getEmailsTo(email);
      for (const msg of emails) {
        if (this.verifyLinkExists(msg, regex)) {
          return msg;
        }
      }
      await this.page.waitForTimeout(1000);
    }
    throw new Error(`Timeout waiting for email with link matching ${linkPattern} to ${email}`);
  }

  // =============================================================================
  // Private Helper Methods
  // =============================================================================

  /**
   * Strip HTML tags from text
   * @private
   * @param {string} html - HTML string
   * @returns {string} Plain text
   */
  _stripHtml(html) {
    return html
      .replace(/<style[^>]*>.*?<\/style>/gi, '')
      .replace(/<script[^>]*>.*?<\/script>/gi, '')
      .replace(/<[^>]+>/g, '')
      .replace(/&nbsp;/g, ' ')
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .trim();
  }
}

// =============================================================================
// API Test Helpers
// =============================================================================

class ApiTestHelpers {
  constructor(page) {
    this.page = page;
    this.apiUrl = process.env.API_URL || 'http://localhost:8000';
  }

  /**
   * Make authenticated API request
   * @param {string} method - HTTP method
   * @param {string} path - API path
   * @param {object} options - Request options
   */
  async request(method, path, options = {}) {
    const url = `${this.apiUrl}${path}`;
    return this.page.request[method.toLowerCase()](url, options);
  }

  /**
   * Get API health status
   */
  async getHealthStatus() {
    const response = await this.request('GET', '/health');
    return response.json();
  }

  /**
   * Wait for API to be ready
   * @param {number} timeout - Timeout in ms
   */
  async waitForApiReady(timeout = 30000) {
    const startTime = Date.now();
    while (Date.now() - startTime < timeout) {
      try {
        const response = await this.request('GET', '/health');
        if (response.ok) {
          return true;
        }
      } catch {
        // API not ready yet
      }
      await this.page.waitForTimeout(1000);
    }
    throw new Error('API did not become ready in time');
  }
}

/**
 * Standalone login helper function for backward compatibility
 * @param {Page} page - Playwright page object
 * @param {string} email - User email
 * @param {string} password - User password
 */
async function loginAs(page, email, password) {
  const auth = new AuthHelpers(page);
  await auth.login(email, password);
}

/**
 * Wait for an element to appear on the page
 * @param {Page} page - Playwright page object
 * @param {string} selector - CSS selector
 * @param {number} timeout - Timeout in ms
 */
async function waitForElement(page, selector, timeout = 10000) {
  await page.waitForSelector(selector, { timeout });
}

/**
 * Generate a unique test email address
 * @param {string} prefix - Prefix for the email address
 * @returns {string} Unique email address
 */
function generateTestEmail(prefix = 'test') {
  const timestamp = Date.now();
  const random = Math.random().toString(36).substring(2, 8);
  return `${prefix}-${timestamp}-${random}@test.marty.demo`;
}

module.exports = {
  DemoTestHelpers,
  AuthHelpers,
  MobileWalletHelpers,
  WalletBridge,
  PushNotificationHelpers,
  DeviceRegistrationHelpers,
  MailHogHelpers,
  MockEmailHelpers,
  EmailTestHelpers,
  ApiTestHelpers,
  mockCredentialData,
  mockVerifiablePresentation,
  mockApiResponses,
  // Standalone helper functions
  loginAs,
  waitForElement,
  generateTestEmail,
  // RSA signing utilities
  generateTestKeypair,
  signChallenge,
  // Re-export user fixtures
  SEEDED_USERS,
  SEEDED_PASSWORDS,
  SEEDED_ORGS,
  getUserByRole,
};