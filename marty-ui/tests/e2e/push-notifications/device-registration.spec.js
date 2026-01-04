/**
 * Device Registration Tests
 * 
 * Tests for mobile device registration for push notifications.
 * Uses mock device IDs and Firebase tokens.
 * 
 * Tests the /api/devices/register endpoint
 */
const { test, expect } = require('@playwright/test');
const { 
  AuthHelpers, 
  DeviceRegistrationHelpers,
  SEEDED_USERS 
} = require('../../utils/test-helpers');

test.describe('Device Registration API', () => {
  let auth;
  let deviceReg;

  test.beforeEach(async ({ page }) => {
    auth = new AuthHelpers(page);
    deviceReg = new DeviceRegistrationHelpers(page);
    
    await page.goto('/');
    await auth.loginAsSeededUser('applicant1');
  });

  test('can register a new device', async ({ page }) => {
    const userId = SEEDED_USERS.applicant1.email;
    const deviceId = deviceReg.generateDeviceId('test-org-123', 'android');
    const fcmToken = deviceReg.generateMockFcmToken();
    
    const result = await deviceReg.registerDevice(userId, {
      deviceId,
      fcmToken,
      platform: 'android',
      appVersion: '1.0.0',
      osVersion: 'Android 14',
      deviceModel: 'Pixel 8',
    });
    
    expect(result.device_id).toBe(deviceId);
    expect(result.registration_id).toBeTruthy();
    expect(result.organization_id).toBe('test-org-123');
  });

  test('can update existing device registration', async ({ page }) => {
    const userId = SEEDED_USERS.applicant1.email;
    const deviceId = deviceReg.generateDeviceId(null, 'ios');
    
    // Register initially
    const firstToken = deviceReg.generateMockFcmToken();
    const firstResult = await deviceReg.registerDevice(userId, {
      deviceId,
      fcmToken: firstToken,
      platform: 'ios',
    });
    
    // Update with new token
    const secondToken = deviceReg.generateMockFcmToken();
    const secondResult = await deviceReg.registerDevice(userId, {
      deviceId,
      fcmToken: secondToken,
      platform: 'ios',
    });
    
    // Should reuse same registration
    expect(secondResult.device_id).toBe(deviceId);
    expect(secondResult.registration_id).toBe(firstResult.registration_id);
  });

  test('can list registered devices', async ({ page }) => {
    const userId = SEEDED_USERS.applicant1.email;
    
    // Register a few devices
    await deviceReg.registerDevice(userId, {
      deviceId: deviceReg.generateDeviceId(null, 'android'),
      fcmToken: deviceReg.generateMockFcmToken(),
      platform: 'android',
    });
    
    await deviceReg.registerDevice(userId, {
      deviceId: deviceReg.generateDeviceId(null, 'ios'),
      fcmToken: deviceReg.generateMockFcmToken(),
      platform: 'ios',
    });
    
    // List devices
    const devices = await deviceReg.getUserDevices(userId);
    
    expect(devices.length).toBeGreaterThanOrEqual(2);
    expect(devices.some(d => d.device_id.includes('android'))).toBe(true);
    expect(devices.some(d => d.device_id.includes('ios'))).toBe(true);
  });

  test('can filter devices by organization', async ({ page }) => {
    const userId = SEEDED_USERS.applicant1.email;
    const orgId = `org-${Date.now()}`;
    
    // Register device for specific org
    await deviceReg.registerDevice(userId, {
      deviceId: deviceReg.generateDeviceId(orgId, 'web'),
      fcmToken: deviceReg.generateMockFcmToken(),
      platform: 'web',
    });
    
    // Register device without org
    await deviceReg.registerDevice(userId, {
      deviceId: deviceReg.generateDeviceId(null, 'android'),
      fcmToken: deviceReg.generateMockFcmToken(),
      platform: 'android',
    });
    
    // List only org devices
    const orgDevices = await deviceReg.getUserDevices(userId, orgId);
    
    expect(orgDevices.length).toBe(1);
    expect(orgDevices[0].device_id).toContain(orgId);
  });

  test('can unregister a device', async ({ page }) => {
    const userId = SEEDED_USERS.applicant1.email;
    const deviceId = deviceReg.generateDeviceId(null, 'web');
    
    // Register
    await deviceReg.registerDevice(userId, {
      deviceId,
      fcmToken: deviceReg.generateMockFcmToken(),
      platform: 'web',
    });
    
    // Verify exists
    let devices = await deviceReg.getUserDevices(userId);
    expect(devices.some(d => d.device_id === deviceId)).toBe(true);
    
    // Unregister
    const success = await deviceReg.unregisterDevice(userId, deviceId);
    expect(success).toBe(true);
    
    // Verify removed
    devices = await deviceReg.getUserDevices(userId);
    expect(devices.some(d => d.device_id === deviceId)).toBe(false);
  });

  test('device ID format is validated', async ({ page }) => {
    const userId = SEEDED_USERS.applicant1.email;
    
    // Valid formats
    const validIds = [
      'simple-device-id',
      'org-123:device-456',
      '550e8400-e29b-41d4-a716-446655440000:abc123',
    ];
    
    for (const deviceId of validIds) {
      const result = await deviceReg.registerDevice(userId, {
        deviceId,
        fcmToken: deviceReg.generateMockFcmToken(),
        platform: 'android',
      });
      expect(result.device_id).toBe(deviceId);
    }
  });
});

test.describe('Device Registration from Mobile Wallet', () => {
  // These tests simulate the mobile wallet's perspective
  
  test('mobile wallet iframe can register device via API', async ({ page }) => {
    // Test the API directly
    const apiUrl = process.env.API_URL || 'http://localhost:8000';
    const userId = SEEDED_USERS.applicant1.email;
    const deviceId = `test-org:wallet-device-${Date.now()}`;
    
    const response = await page.request.post(`${apiUrl}/api/devices/register`, {
      headers: {
        'Content-Type': 'application/json',
        'X-User-ID': userId,
      },
      data: {
        device_id: deviceId,
        fcm_token: 'test-fcm-token',
        platform: 'web',
        app_version: '1.0.0-test',
      },
    });
    
    expect(response.status()).toBe(201);
    
    const result = await response.json();
    expect(result.device_id).toBe(deviceId);
    expect(result.organization_id).toBe('test-org');
    expect(result.registration_id).toBeTruthy();
  });
});
