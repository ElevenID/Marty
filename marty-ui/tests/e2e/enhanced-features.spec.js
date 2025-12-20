const { test, expect } = require('@playwright/test');
const { DemoTestHelpers, mockApiResponses } = require('../utils/test-helpers');

// SKIPPED: These tests are for the OpenWallet Foundation mDoc/mDL Demo UI
// which has an "Enhanced" tab with Age Verification, Offline QR, Certificate Monitoring, and Policy Engine.
// The current app is "Marty Trust Services" with different features.
// Re-enable when these features are integrated or these tests are updated.
test.describe.skip('Enhanced Features Tests', () => {
  let helpers;

  test.beforeEach(async ({ page }) => {
    helpers = new DemoTestHelpers(page);
    await page.goto('/');
    await helpers.waitForPageLoad();
    await helpers.navigateToTab('Enhanced');
  });

  test.describe('Enhanced Features Navigation', () => {
    test('should display enhanced features interface', async ({ page }) => {
      await expect(page.locator('h4')).toContainText('Enhanced mDoc/mDL Verifier Demo');
      await expect(page.locator('text=Explore advanced mDoc/mDL verification capabilities')).toBeVisible();

      // Verify feature tabs are present
      await expect(page.locator('button:has-text("Age Verification")')).toBeVisible();
      await expect(page.locator('button:has-text("Offline QR")')).toBeVisible();
      await expect(page.locator('button:has-text("Certificate Monitor")')).toBeVisible();
      await expect(page.locator('button:has-text("Policy Engine")')).toBeVisible();
    });

    test('should navigate between enhanced feature tabs', async ({ page }) => {
      const features = ['Age Verification', 'Offline QR', 'Certificate Monitor', 'Policy Engine'];

      for (const feature of features) {
        await helpers.clickButton(feature);

        // Verify the feature content is loaded
        await expect(page.locator('h6')).toBeVisible();

        // Verify active button state
        const activeButton = page.locator(`button:has-text("${feature}")[variant="contained"]`);
        await expect(activeButton).toBeVisible();
      }
    });
  });

  test.describe('Age Verification Feature', () => {
    test.beforeEach(async ({ page }) => {
      await helpers.clickButton('Age Verification');
    });

    test('should display age verification interface', async ({ page }) => {
      await expect(page.locator('h6')).toContainText('Enhanced Age Verification Demo');
      await expect(page.locator('text=Verify age without disclosing birth date')).toBeVisible();

      // Verify sections are present
      await helpers.verifyCardContent('1. Create Verification Request', 'Use Case');
      await helpers.verifyCardContent('2. Simulate Verification', '');
    });

    test('should complete age verification flow for alcohol purchase', async ({ page }) => {
      // Mock the API responses
      await helpers.mockApiResponse('**/api/verifier/age-verification/request', {
        success: true,
        verification_request: {
          request_id: 'req_123',
          use_case: 'alcohol_purchase',
          age_threshold: 21
        }
      });

      await helpers.mockApiResponse('**/api/verifier/age-verification/verify', mockApiResponses.ageVerificationSuccess);

      // Select use case
      await helpers.selectAgeVerificationUseCase('Alcohol Purchase (21+)');

      // Create request
      await helpers.clickButton('Create Request');

      // Verify request created
      await helpers.waitForAlert('info');
      await expect(page.locator('text=Request created for: Alcohol Purchase')).toBeVisible();

      // Simulate verification
      await helpers.clickButton('Simulate Verification');

      // Verify results
      await expect(page.locator('text=Verification Result')).toBeVisible();
      await helpers.verifyChipStatus('VERIFIED', 'success');
      await helpers.verifyChipStatus('Privacy: HIGH', 'success');

      // Verify privacy report
      await helpers.expandAccordion('Privacy Report');
      await expect(page.locator('pre')).toContainText('privacy_level');
    });

    test('should test different age verification use cases', async ({ page }) => {
      const useCases = [
        'Voting Registration (18+)',
        'Senior Discount (65+)',
        'Employment Eligibility (18-65)'
      ];

      for (const useCase of useCases) {
        // Mock responses for each use case
        await helpers.mockApiResponse('**/api/verifier/age-verification/request', {
          success: true,
          verification_request: { request_id: `req_${Date.now()}`, use_case: useCase.toLowerCase().replace(/\s+/g, '_') }
        });

        await helpers.selectAgeVerificationUseCase(useCase);
        await helpers.clickButton('Create Request');

        // Verify request created for each use case
        await helpers.waitForAlert('info');
        await expect(page.locator(`text=Request created for: ${useCase.split(' (')[0]}`)).toBeVisible();
      }
    });

    test('should handle age verification errors gracefully', async ({ page }) => {
      // Mock error response
      await helpers.mockApiResponse('**/api/verifier/age-verification/request', {
        success: false,
        error: 'Age verification service unavailable'
      });

      await helpers.selectAgeVerificationUseCase('Alcohol Purchase (21+)');
      await helpers.clickButton('Create Request');

      // Should handle error gracefully (exact behavior depends on implementation)
      await page.waitForTimeout(2000);
    });
  });

  test.describe('Offline QR Feature', () => {
    test.beforeEach(async ({ page }) => {
      await helpers.clickButton('Offline QR');
    });

    test('should display offline QR interface', async ({ page }) => {
      await expect(page.locator('h6')).toContainText('Offline QR Code Verification Demo');
      await expect(page.locator('text=Create and verify QR codes that work without network')).toBeVisible();

      // Verify sections
      await helpers.verifyCardContent('1. Create Offline QR Code', 'Generate Offline QR');
      await helpers.verifyCardContent('2. Verify Offline', 'Verify Offline QR');
    });

    test('should create and verify offline QR code', async ({ page }) => {
      // Mock QR creation response
      await helpers.mockApiResponse('**/api/verifier/offline-qr/create', mockApiResponses.offlineQRSuccess);

      // Mock QR verification response
      await helpers.mockApiResponse('**/api/verifier/offline-qr/verify', {
        verification_result: {
          verified: true,
          checks_performed: [
            { check_name: 'CBOR Decode', passed: true, details: 'Successfully decoded CBOR data' },
            { check_name: 'Signature Verify', passed: true, details: 'Valid ECDSA signature' },
            { check_name: 'Timestamp Check', passed: true, details: 'QR code not expired' }
          ]
        }
      });

      // Create QR code
      await helpers.clickButton('Generate Offline QR');

      // Verify QR creation success
      await helpers.waitForAlert('success');
      await expect(page.locator('text=QR Code created!')).toBeVisible();
      await expect(page.locator('text=Size: 1024 bytes')).toBeVisible();

      // Verify QR image is displayed
      await helpers.verifyQRCodeGenerated();

      // Verify offline QR
      await helpers.clickButton('Verify Offline QR');

      // Verify verification results
      await helpers.verifyChipStatus('VERIFIED', 'success');

      // Verify verification details
      await helpers.expandAccordion('Verification Details');
      await expect(page.locator('text=CBOR Decode')).toBeVisible();
      await expect(page.locator('text=Signature Verify')).toBeVisible();
      await expect(page.locator('text=Timestamp Check')).toBeVisible();
    });

    test('should disable verify button when no QR code exists', async ({ page }) => {
      const verifyButton = page.locator('button:has-text("Verify Offline QR")');
      await expect(verifyButton).toBeDisabled();
    });

    test('should show QR code details', async ({ page }) => {
      // Mock QR creation
      await helpers.mockApiResponse('**/api/verifier/offline-qr/create', mockApiResponses.offlineQRSuccess);

      await helpers.clickButton('Generate Offline QR');
      await helpers.waitForAlert('success');

      // Verify QR details are shown
      await expect(page.locator('text=Size:')).toBeVisible();
      await expect(page.locator('img[alt*="Offline QR"]')).toBeVisible();
    });
  });

  test.describe('Certificate Monitoring Feature', () => {
    test.beforeEach(async ({ page }) => {
      await helpers.clickButton('Certificate Monitor');
    });

    test('should display certificate monitoring interface', async ({ page }) => {
      await expect(page.locator('h6')).toContainText('Certificate Lifecycle Monitoring');
      await expect(page.locator('text=Monitor mDL Document Signer Certificate expiry')).toBeVisible();
    });

    test('should load and display certificate dashboard', async ({ page }) => {
      // Mock certificate dashboard response
      await helpers.mockApiResponse('**/api/verifier/certificates/dashboard', mockApiResponses.certificateDashboard);

      // Wait for dashboard to load
      await page.waitForTimeout(1000);

      // Verify overview cards
      await expect(page.locator('text=Total Certificates')).toBeVisible();
      await expect(page.locator('text=Critical Alerts')).toBeVisible();
      await expect(page.locator('text=Need Renewal')).toBeVisible();
      await expect(page.locator('text=Expired')).toBeVisible();

      // Verify certificate list
      await expect(page.locator('text=Demo DMV DSC')).toBeVisible();
      await expect(page.locator('text=Test Authority DSC')).toBeVisible();

      // Verify status indicators
      await expect(page.locator('[data-testid="ErrorIcon"]')).toBeVisible(); // Critical status
      await expect(page.locator('[data-testid="WarningIcon"]')).toBeVisible(); // Expiring soon
    });

    test('should handle certificate renewal', async ({ page }) => {
      // Mock dashboard and renewal responses
      await helpers.mockApiResponse('**/api/verifier/certificates/dashboard', mockApiResponses.certificateDashboard);
      await helpers.mockApiResponse('**/api/verifier/certificates/*/renew', {
        renewal_successful: true,
        new_expiry_date: '2025-12-31'
      });

      await page.waitForTimeout(1000); // Wait for dashboard load

      // Mock alert dialog
      page.on('dialog', dialog => dialog.accept());

      // Click renew on first certificate
      await page.locator('button:has-text("Renew")').first().click();

      // Should trigger renewal process
      await page.waitForTimeout(1000);
    });

    test('should show certificate overview metrics', async ({ page }) => {
      await helpers.mockApiResponse('**/api/verifier/certificates/dashboard', mockApiResponses.certificateDashboard);

      await page.waitForTimeout(1000);

      // Verify overview numbers match mock data
      await expect(page.locator('text=5')).toBeVisible(); // Total certificates
      await expect(page.locator('text=1')).toBeVisible(); // Critical alerts
      await expect(page.locator('text=2')).toBeVisible(); // Need renewal
    });
  });

  test.describe('Policy Engine Feature', () => {
    test.beforeEach(async ({ page }) => {
      await helpers.clickButton('Policy Engine');
    });

    test('should display policy engine interface', async ({ page }) => {
      await expect(page.locator('h6')).toContainText('Policy-Based Selective Disclosure');
      await expect(page.locator('text=Context-aware attribute sharing')).toBeVisible();

      // Verify sections
      await helpers.verifyCardContent('Available Policies', '');
      await helpers.verifyCardContent('Policy Evaluation', 'Evaluate Demo Policy');
    });

    test('should load and display available policies', async ({ page }) => {
      // Mock policy summary response
      await helpers.mockApiResponse('**/api/verifier/policy/summary', {
        policies: {
          commercial_standard: {
            name: 'Commercial Standard',
            context_type: 'commercial',
            purpose: 'age_verification',
            privacy_level: 'standard'
          },
          government_high: {
            name: 'Government High Security',
            context_type: 'government',
            purpose: 'identity_verification',
            privacy_level: 'high'
          }
        }
      });

      await page.waitForTimeout(1000); // Wait for policies to load

      // Verify policies are displayed
      await expect(page.locator('text=Commercial Standard')).toBeVisible();
      await expect(page.locator('text=Government High Security')).toBeVisible();
      await expect(page.locator('text=commercial • age_verification • Privacy: standard')).toBeVisible();
    });

    test('should evaluate demo policy', async ({ page }) => {
      // Mock policy evaluation response
      await helpers.mockApiResponse('**/api/verifier/policy/evaluate', mockApiResponses.policyEvaluation);

      // Evaluate policy
      await helpers.clickButton('Evaluate Demo Policy');

      // Verify evaluation results
      await helpers.verifyChipStatus('APPROVE', 'success');

      // Verify evaluation details
      await helpers.expandAccordion('Evaluation Details');
      await expect(page.locator('pre')).toContainText('recommended_action');
      await expect(page.locator('pre')).toContainText('disclosed_attributes');
      await expect(page.locator('pre')).toContainText('privacy_score');
    });

    test('should reload policies', async ({ page }) => {
      await helpers.mockApiResponse('**/api/verifier/policy/summary', {
        policies: {
          test_policy: {
            name: 'Test Policy',
            context_type: 'test',
            purpose: 'testing',
            privacy_level: 'high'
          }
        }
      });

      await helpers.clickButton('Reload Policies');

      await page.waitForTimeout(1000);
      // Should reload the policies list
    });
  });

  test.describe('Enhanced Features Integration', () => {
    test('should work seamlessly between features', async ({ page }) => {
      // Test switching between different enhanced features
      const features = ['Age Verification', 'Offline QR', 'Certificate Monitor', 'Policy Engine'];

      for (const feature of features) {
        await helpers.clickButton(feature);
        await expect(page.locator('h6')).toBeVisible();

        // Each feature should load without errors
        const errorElements = page.locator('[role="alert"][data-severity="error"]');
        await expect(errorElements).toHaveCount(0);
      }
    });

    test('should handle API errors gracefully across features', async ({ page }) => {
      // Mock error responses for various APIs
      await page.route('**/api/verifier/age-verification/**', route => {
        route.fulfill({ status: 503, body: JSON.stringify({ error: 'Service unavailable' }) });
      });

      await page.route('**/api/verifier/offline-qr/**', route => {
        route.fulfill({ status: 503, body: JSON.stringify({ error: 'Service unavailable' }) });
      });

      // Test that features handle errors gracefully
      await helpers.clickButton('Age Verification');
      await helpers.selectAgeVerificationUseCase('Alcohol Purchase (21+)');
      await helpers.clickButton('Create Request');

      // Should not crash the application
      await expect(page.locator('h6')).toContainText('Enhanced Age Verification Demo');
    });

    test('should maintain state when switching features', async ({ page }) => {
      // Test Age Verification
      await helpers.clickButton('Age Verification');
      await helpers.selectAgeVerificationUseCase('Voting Registration (18+)');

      // Switch to another feature
      await helpers.clickButton('Offline QR');

      // Switch back to Age Verification
      await helpers.clickButton('Age Verification');

      // State should be maintained (use case selection)
      const selectElement = page.locator('[role="button"]:has-text("Use Case")');
      await expect(selectElement).toBeVisible();
    });
  });

  test.describe('Enhanced Features Performance', () => {
    test('should load enhanced features quickly', async ({ page }) => {
      const startTime = Date.now();

      await helpers.clickButton('Age Verification');
      await expect(page.locator('h6')).toContainText('Enhanced Age Verification Demo');

      const loadTime = Date.now() - startTime;
      expect(loadTime).toBeLessThan(3000); // Should load within 3 seconds
    });

    test('should handle multiple rapid feature switches', async ({ page }) => {
      const features = ['Age Verification', 'Offline QR', 'Certificate Monitor', 'Policy Engine'];

      // Rapidly switch between features
      for (let i = 0; i < 3; i++) {
        for (const feature of features) {
          await helpers.clickButton(feature);
          await page.waitForTimeout(100); // Brief pause
        }
      }

      // Should still be functional
      await expect(page.locator('h6')).toBeVisible();
    });
  });
});
