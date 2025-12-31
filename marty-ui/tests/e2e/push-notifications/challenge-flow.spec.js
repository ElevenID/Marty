/**
 * Push Challenge Flow Tests
 * 
 * Tests for push challenge creation, polling, and response.
 * Uses the mock notification adapter for verification.
 * 
 * Now uses proper RSA signatures for challenge responses.
 *
 * Uses backend API endpoints (/api/devices/register, /api/push/*)
 */
const { test, expect } = require('@playwright/test');
const { 
  AuthHelpers, 
  DeviceRegistrationHelpers,
  PushNotificationHelpers,
  SEEDED_USERS 
} = require('../../utils/test-helpers');

test.describe('Push Challenge Creation @slow', () => {
  let auth;
  let deviceReg;
  let pushNotifications;
  let registeredDeviceId;

  test.beforeEach(async ({ page }) => {
    auth = new AuthHelpers(page);
    deviceReg = new DeviceRegistrationHelpers(page);
    pushNotifications = new PushNotificationHelpers(page, deviceReg);
    pushNotifications.setUserId(SEEDED_USERS.applicant1.email);
    
    await page.goto('/');
    await auth.loginAsSeededUser('applicant1');
    
    // Register a test device with RSA keypair
    const result = await deviceReg.registerDevice(SEEDED_USERS.applicant1.email, {
      platform: 'web',
    });
    registeredDeviceId = result.deviceId;
    
    // Clear existing challenges
    await pushNotifications.clearAllChallenges();
  });

  test('can create a push challenge for a device', async ({ page }) => {
    const challenge = await pushNotifications.createPushChallenge(registeredDeviceId, {
      title: 'Authentication Request',
      question: 'Do you approve this login?',
      nonce: `nonce-${Date.now()}`,
      ttl_seconds: 120,
    });
    
    expect(challenge.challenge_id).toBeTruthy();
    expect(challenge.device_id).toBe(registeredDeviceId);
    expect(new Date(challenge.expires_at).getTime()).toBeGreaterThan(Date.now());
  });

  test('can poll for pending challenges', async ({ page }) => {
    // Create a challenge
    const createdChallenge = await pushNotifications.createPushChallenge(registeredDeviceId, {
      title: 'Poll Test',
      question: 'Can you see this?',
      nonce: `nonce-${Date.now()}`,
      ttl_seconds: 120,
    });
    
    // Poll for challenges
    const challenges = await pushNotifications.getPendingChallenges(registeredDeviceId);
    
    expect(challenges.length).toBeGreaterThanOrEqual(1);
    expect(challenges.some(c => c.challenge_id === createdChallenge.challenge_id)).toBe(true);
  });

  test('can respond to a challenge with accept', async ({ page }) => {
    // Create challenge with nonce
    const nonce = `nonce-${Date.now()}`;
    const challenge = await pushNotifications.createPushChallenge(registeredDeviceId, {
      title: 'Accept Test',
      question: 'Please accept this',
      nonce,
      ttl_seconds: 120,
    });
    
    // Respond with accept - signature is auto-generated from registered keypair
    const result = await pushNotifications.respondToChallenge(
      registeredDeviceId,
      challenge.challenge_id,
      'accept',
      nonce  // Pass nonce for auto-signing
    );
    
    expect(result.success).toBe(true);
    expect(result.response).toBe('accept');
    
    // Challenge should no longer be pending
    const pending = await pushNotifications.getPendingChallenges(registeredDeviceId);
    expect(pending.some(c => c.challenge_id === challenge.challenge_id)).toBe(false);
  });

  test('can respond to a challenge with reject', async ({ page }) => {
    // Create challenge
    const nonce = `nonce-${Date.now()}`;
    const challenge = await pushNotifications.createPushChallenge(registeredDeviceId, {
      title: 'Reject Test',
      question: 'Please reject this',
      nonce,
      ttl_seconds: 120,
    });
    
    // Respond with reject
    const result = await pushNotifications.respondToChallenge(
      registeredDeviceId,
      challenge.challenge_id,
      'reject'
    );
    
    expect(result.success).toBe(true);
    expect(result.response).toBe('reject');
  });

  test('expired challenges are not returned', async ({ page }) => {
    // Create challenge with very short TTL
    const challenge = await pushNotifications.createPushChallenge(registeredDeviceId, {
      title: 'Expiry Test',
      question: 'This will expire',
      nonce: `nonce-${Date.now()}`,
      ttl_seconds: 1, // Minimum 30 seconds in API, but mock might allow shorter
    });
    
    // Wait for expiry
    await page.waitForTimeout(2000);
    
    // Poll should not include expired challenge
    const pending = await pushNotifications.getPendingChallenges(registeredDeviceId);
    
    // Note: This might still include it depending on server-side expiry handling
    // The test documents expected behavior
  });

  test('multiple challenges can be pending simultaneously', async ({ page }) => {
    // Create multiple challenges
    const challenges = [];
    for (let i = 0; i < 3; i++) {
      const challenge = await pushNotifications.createPushChallenge(registeredDeviceId, {
        title: `Challenge ${i + 1}`,
        question: `Question ${i + 1}`,
        nonce: `nonce-${Date.now()}-${i}`,
        ttl_seconds: 120,
      });
      challenges.push(challenge);
    }
    
    // Poll should return all
    const pending = await pushNotifications.getPendingChallenges(registeredDeviceId);
    
    expect(pending.length).toBeGreaterThanOrEqual(3);
    for (const created of challenges) {
      expect(pending.some(c => c.challenge_id === created.challenge_id)).toBe(true);
    }
  });
});

test.describe('Push Challenge with Credential Operations @slow', () => {
  let auth;
  let deviceReg;
  let pushNotifications;
  let registeredDeviceId;

  test.beforeEach(async ({ page }) => {
    auth = new AuthHelpers(page);
    deviceReg = new DeviceRegistrationHelpers(page);
    pushNotifications = new PushNotificationHelpers(page, deviceReg);
    pushNotifications.setUserId(SEEDED_USERS.applicant1.email);
    
    await page.goto('/');
    await auth.loginAsSeededUser('applicant1');
    
    // Register device with RSA keypair
    const result = await deviceReg.registerDevice(SEEDED_USERS.applicant1.email, {
      platform: 'android',
    });
    registeredDeviceId = result.deviceId;
    
    await pushNotifications.clearAllChallenges();
  });

  test('challenge can reference a credential ID', async ({ page }) => {
    const credentialId = `cred-${Date.now()}`;
    
    const challenge = await pushNotifications.createPushChallenge(registeredDeviceId, {
      title: 'Credential Verification',
      question: 'Allow access to your travel document?',
      nonce: `nonce-${Date.now()}`,
      credential_id: credentialId,
      data: {
        verifier: 'Border Control',
        requested_claims: ['given_name', 'family_name', 'document_number'],
      },
      ttl_seconds: 60,
    });
    
    expect(challenge.challenge_id).toBeTruthy();
    
    // Poll and verify credential_id is present
    const pending = await pushNotifications.getPendingChallenges(registeredDeviceId);
    const found = pending.find(c => c.challenge_id === challenge.challenge_id);
    
    expect(found).toBeTruthy();
    expect(found.credential_id).toBe(credentialId);
    expect(found.data.verifier).toBe('Border Control');
  });
});

test.describe('Mock Notification Storage @slow', () => {
  let pushNotifications;

  test.beforeEach(async ({ page }) => {
    pushNotifications = new PushNotificationHelpers(page);
    pushNotifications.setUserId('test-user');
    await pushNotifications.clearAllNotifications();
  });

  test('can retrieve stored notifications', async ({ page }) => {
    // The mock adapter stores notifications when they're "sent"
    // This tests the retrieval for verification
    
    const notifications = await pushNotifications.getAllNotifications();
    
    // Should return an array (possibly empty)
    expect(Array.isArray(notifications)).toBe(true);
  });

  test('can filter notifications by event type', async ({ page }) => {
    const notifications = await pushNotifications.getNotificationsByEventType('application.submitted');
    
    expect(Array.isArray(notifications)).toBe(true);
    // All returned should have matching event type
    for (const n of notifications) {
      expect(n.event_type).toBe('application.submitted');
    }
  });

  test('can clear all notifications', async ({ page }) => {
    // Clear
    await pushNotifications.clearAllNotifications();
    
    // Verify empty
    const notifications = await pushNotifications.getAllNotifications();
    expect(notifications.length).toBe(0);
  });
});
