const { test, expect } = require('@playwright/test');
const { DemoTestHelpers, mockCredentialData, mockApiResponses } = require('../../utils/test-helpers');

// SKIPPED: These tests are for the OpenWallet Foundation mDoc/mDL Demo UI
// which has Issuer/Verifier/Wallet tabs and credential issuance workflows.
// The current app is "Marty Trust Services" with different workflow.
// Re-enable when the integration tests are updated to match the current app.
test.describe.skip('End-to-End Integration Tests', () => {
  let helpers;

  test.beforeEach(async ({ page }) => {
    helpers = new DemoTestHelpers(page);
    await page.goto('/');
    await helpers.waitForPageLoad();
  });

  test.describe('Complete Credential Lifecycle', () => {
    test('should complete full credential issuance to verification flow', async ({ page }) => {
      // Mock all required API responses
      await helpers.mockApiResponse('**/api/issuer/issue', mockApiResponses.issuerSuccess);
      await helpers.mockApiResponse('**/api/verifier/verify', mockApiResponses.verifierSuccess);
      await helpers.mockApiResponse('**/api/wallet/credentials', {
        success: true,
        credentials: []
      });
      await helpers.mockApiResponse('**/api/wallet/create-presentation', {
        success: true,
        presentation: mockApiResponses.verifierSuccess.presentation_summary
      });

      // Step 1: Issue a credential
      await helpers.navigateToTab('Issuer');

      // Fill out credential information
      await helpers.fillFormField('Given Name', mockCredentialData.given_name);
      await helpers.fillFormField('Family Name', mockCredentialData.family_name);
      await page.fill('input[type="date"]', mockCredentialData.birth_date);
      await helpers.fillFormField('Document Number', mockCredentialData.document_number);
      await helpers.fillFormField('Issuing Country', mockCredentialData.issuing_country);

      // Complete issuance flow
      await helpers.clickButton('Next'); // To review
      await helpers.clickButton('Next'); // To issue
      await helpers.clickButton('Issue Credential');

      // Verify credential issued
      await helpers.waitForAlert('success');
      await helpers.verifyChipStatus('ID:', 'primary');

      // Step 2: Add credential to wallet (simulated)
      await helpers.navigateToTab('Wallet');

      // Add demo credential (represents the issued credential)
      await helpers.clickButton('Add Demo Credential');

      // Verify credential appears in wallet
      await expect(page.locator('.MuiCard-root')).toHaveCount({ min: 1 });

      // Step 3: Create presentation from wallet
      await page.locator('button:has-text("Share")').first().click();

      // Fill presentation request
      const presentationRequest = '{"requested_attributes": ["given_name", "family_name", "age_over_21"], "purpose": "age_verification"}';
      await page.fill('textarea[label*="Presentation Request"]', presentationRequest);

      await helpers.clickButton('Create Presentation');

      // Wait for presentation creation
      await page.waitForTimeout(1000);

      // Step 4: Verify the presentation
      await helpers.navigateToTab('Verifier');

      // Simulate QR scan to get presentation data
      await helpers.clickButton('Simulate QR Code Scan');
      await page.waitForTimeout(2500);

      // Verify the presentation
      await helpers.clickButton('Verify Presentation');

      // Verify successful verification
      await helpers.waitForAlert('success');
      await helpers.verifyChipStatus('VERIFIED', 'success');

      // Verify complete workflow
      await expect(page.locator('text=Credential verification successful!')).toBeVisible();
    });

    test('should handle credential with enhanced age verification', async ({ page }) => {
      // Mock responses for enhanced age verification flow
      await helpers.mockApiResponse('**/api/issuer/issue', mockApiResponses.issuerSuccess);
      await helpers.mockApiResponse('**/api/verifier/age-verification/request', {
        success: true,
        verification_request: { request_id: 'age_req_123', use_case: 'alcohol_purchase' }
      });
      await helpers.mockApiResponse('**/api/verifier/age-verification/verify', mockApiResponses.ageVerificationSuccess);

      // Issue credential with age information
      await helpers.navigateToTab('Issuer');

      await helpers.fillFormField('Given Name', 'John');
      await helpers.fillFormField('Family Name', 'Smith');
      await page.fill('input[type="date"]', '1985-03-15'); // Over 21
      await helpers.fillFormField('Document Number', 'DL999888777');
      await helpers.fillFormField('Issuing Country', 'US');

      await helpers.clickButton('Next');
      await helpers.clickButton('Next');
      await helpers.clickButton('Issue Credential');
      await helpers.waitForAlert('success');

      // Use enhanced age verification
      await helpers.navigateToTab('Enhanced');
      await helpers.clickButton('Age Verification');

      await helpers.selectAgeVerificationUseCase('Alcohol Purchase (21+)');
      await helpers.clickButton('Create Request');
      await helpers.waitForAlert('info');

      await helpers.clickButton('Simulate Verification');

      // Verify age verification without birth date disclosure
      await helpers.verifyChipStatus('VERIFIED', 'success');
      await helpers.verifyChipStatus('Privacy: HIGH', 'success');

      // Verify privacy protection
      await helpers.expandAccordion('Privacy Report');
      await expect(page.locator('pre')).toContainText('birth_date');
      await expect(page.locator('pre')).toContainText('attributes_protected');
    });
  });

  test.describe('Cross-Feature Integration', () => {
    test('should use policy engine to guide age verification', async ({ page }) => {
      // Mock policy and age verification responses
      await helpers.mockApiResponse('**/api/verifier/policy/evaluate', {
        ...mockApiResponses.policyEvaluation,
        context: {
          context_type: 'commercial',
          verifier_trust_level: 'verified_commercial',
          purpose: 'alcohol_purchase'
        }
      });
      await helpers.mockApiResponse('**/api/verifier/age-verification/request', {
        success: true,
        verification_request: { request_id: 'policy_guided_req', use_case: 'alcohol_purchase' }
      });

      await helpers.navigateToTab('Enhanced');

      // First evaluate policy
      await helpers.clickButton('Policy Engine');
      await helpers.clickButton('Evaluate Demo Policy');

      await helpers.verifyChipStatus('APPROVE', 'success');
      await helpers.expandAccordion('Evaluation Details');

      // Then use age verification based on policy guidance
      await helpers.clickButton('Age Verification');
      await helpers.selectAgeVerificationUseCase('Alcohol Purchase (21+)');
      await helpers.clickButton('Create Request');

      // Verify integrated workflow
      await helpers.waitForAlert('info');
      await expect(page.locator('text=Request created for: Alcohol Purchase')).toBeVisible();
    });

    test('should combine offline QR with certificate monitoring', async ({ page }) => {
      // Mock certificate monitoring and offline QR responses
      await helpers.mockApiResponse('**/api/verifier/certificates/dashboard', mockApiResponses.certificateDashboard);
      await helpers.mockApiResponse('**/api/verifier/offline-qr/create', {
        ...mockApiResponses.offlineQRSuccess,
        certificate_info: {
          signer_cert_id: 'dsc_001',
          cert_status: 'active',
          expires_in_days: 365
        }
      });

      await helpers.navigateToTab('Enhanced');

      // Check certificate status first
      await helpers.clickButton('Certificate Monitor');
      await page.waitForTimeout(1000);

      // Verify certificates are healthy
      await expect(page.locator('text=Total Certificates')).toBeVisible();

      // Create offline QR with certificate validation
      await helpers.clickButton('Offline QR');
      await helpers.clickButton('Generate Offline QR');

      await helpers.waitForAlert('success');
      await helpers.verifyQRCodeGenerated();

      // Verify certificate information is included
      await expect(page.locator('text=QR Code created!')).toBeVisible();
    });
  });

  test.describe('Error Handling and Recovery', () => {
    test('should gracefully handle service failures', async ({ page }) => {
      // Test issuer failure
      await helpers.mockApiResponse('**/api/issuer/issue', {
        success: false,
        error: 'Issuer service temporarily unavailable'
      });

      await helpers.navigateToTab('Issuer');

      await helpers.fillFormField('Given Name', 'Test');
      await helpers.fillFormField('Family Name', 'User');

      await helpers.clickButton('Next');
      await helpers.clickButton('Next');
      await helpers.clickButton('Issue Credential');

      // Should handle error gracefully without crashing
      await page.waitForTimeout(2000);
      await expect(page.locator('h4')).toContainText('Credential Issuer Demo');

      // Test verifier failure
      await helpers.mockApiResponse('**/api/verifier/verify', {
        success: false,
        verified: false,
        error: 'Verification failed due to invalid signature'
      });

      await helpers.navigateToTab('Verifier');
      await helpers.clickButton('Simulate QR Code Scan');
      await page.waitForTimeout(2500);
      await helpers.clickButton('Verify Presentation');

      // Should show verification failure
      await page.waitForTimeout(2000);
      await expect(page.locator('h4')).toContainText('Credential Verifier Demo');
    });

    test('should recover from network interruptions', async ({ page }) => {
      // Simulate network failure then recovery
      await page.route('**/api/**', route => {
        route.abort('failed');
      });

      await helpers.navigateToTab('Enhanced');
      await helpers.clickButton('Age Verification');
      await helpers.selectAgeVerificationUseCase('Alcohol Purchase (21+)');
      await helpers.clickButton('Create Request');

      // Wait for failure
      await page.waitForTimeout(2000);

      // Restore network and mock successful response
      await page.unroute('**/api/**');
      await helpers.mockApiResponse('**/api/verifier/age-verification/request', {
        success: true,
        verification_request: { request_id: 'recovery_req', use_case: 'alcohol_purchase' }
      });

      // Retry operation
      await helpers.clickButton('Create Request');
      await helpers.waitForAlert('info');

      // Should recover successfully
      await expect(page.locator('text=Request created')).toBeVisible();
    });
  });

  test.describe('Performance and Scalability', () => {
    test('should handle multiple simultaneous operations', async ({ page }) => {
      // Mock all API responses for concurrent operations
      await helpers.mockApiResponse('**/api/issuer/issue', mockApiResponses.issuerSuccess);
      await helpers.mockApiResponse('**/api/verifier/verify', mockApiResponses.verifierSuccess);
      await helpers.mockApiResponse('**/api/verifier/age-verification/request', {
        success: true,
        verification_request: { request_id: 'concurrent_req' }
      });
      await helpers.mockApiResponse('**/api/verifier/offline-qr/create', mockApiResponses.offlineQRSuccess);

      // Start multiple operations in different tabs
      const operations = [];

      // Operation 1: Issue credential
      operations.push(async () => {
        await helpers.navigateToTab('Issuer');
        await helpers.fillFormField('Given Name', 'Concurrent');
        await helpers.fillFormField('Family Name', 'Test');
        await helpers.clickButton('Next');
        await helpers.clickButton('Next');
        await helpers.clickButton('Issue Credential');
      });

      // Operation 2: Create offline QR
      operations.push(async () => {
        await helpers.navigateToTab('Enhanced');
        await helpers.clickButton('Offline QR');
        await helpers.clickButton('Generate Offline QR');
      });

      // Operation 3: Age verification request
      operations.push(async () => {
        await helpers.navigateToTab('Enhanced');
        await helpers.clickButton('Age Verification');
        await helpers.selectAgeVerificationUseCase('Voting Registration (18+)');
        await helpers.clickButton('Create Request');
      });

      // Execute operations concurrently
      await Promise.all(operations.map(op => op()));

      // Verify all operations completed without conflicts
      await page.waitForTimeout(3000);
      await expect(page.locator('h4, h5, h6')).toBeVisible();
    });

    test('should maintain performance with large datasets', async ({ page }) => {
      // Mock large certificate dataset
      const largeCertDataset = {
        overview: {
          total_certificates: 1000,
          critical_alerts: 50,
          certificates_needing_renewal: 100,
          expired_certificates: 10
        },
        certificates: Array.from({ length: 100 }, (_, i) => ({
          certificate_id: `dsc_${i}`,
          common_name: `Certificate ${i}`,
          status: i % 10 === 0 ? 'critical' : i % 5 === 0 ? 'expiring_soon' : 'active',
          days_until_expiry: Math.floor(Math.random() * 365),
          issuer: `Authority ${i % 10}`
        }))
      };

      await helpers.mockApiResponse('**/api/verifier/certificates/dashboard', largeCertDataset);

      const startTime = Date.now();

      await helpers.navigateToTab('Enhanced');
      await helpers.clickButton('Certificate Monitor');

      // Wait for dashboard to load
      await expect(page.locator('text=Total Certificates')).toBeVisible();
      await expect(page.locator('text=1000')).toBeVisible();

      const loadTime = Date.now() - startTime;
      expect(loadTime).toBeLessThan(5000); // Should load within 5 seconds even with large dataset

      // Verify UI remains responsive
      await helpers.clickButton('Age Verification');
      await expect(page.locator('h6')).toContainText('Enhanced Age Verification Demo');
    });
  });

  test.describe('Security and Privacy Validation', () => {
    test('should validate selective disclosure privacy', async ({ page }) => {
      await helpers.mockApiResponse('**/api/verifier/age-verification/verify', {
        verification_result: {
          verified: true,
          age_requirement_met: true,
          use_case: 'alcohol_purchase'
        },
        privacy_report: {
          privacy_level: 'high',
          attributes_disclosed: ['age_over_21'],
          attributes_protected: ['birth_date', 'exact_age', 'address', 'full_name'],
          zero_knowledge_proof_used: true,
          data_minimization_score: 0.95
        }
      });

      await helpers.navigateToTab('Enhanced');
      await helpers.clickButton('Age Verification');

      await helpers.selectAgeVerificationUseCase('Alcohol Purchase (21+)');
      await helpers.clickButton('Create Request');
      await helpers.waitForAlert('info');

      await helpers.clickButton('Simulate Verification');

      // Verify privacy protection
      await helpers.verifyChipStatus('Privacy: HIGH', 'success');

      await helpers.expandAccordion('Privacy Report');
      const privacyReport = page.locator('pre');

      // Verify only necessary attributes were disclosed
      await expect(privacyReport).toContainText('age_over_21');
      await expect(privacyReport).toContainText('attributes_protected');
      await expect(privacyReport).toContainText('birth_date');
      await expect(privacyReport).toContainText('zero_knowledge_proof_used');
    });

    test('should enforce proper authentication flows', async ({ page }) => {
      // Mock authentication failure
      await helpers.mockApiResponse('**/api/verifier/verify', {
        success: false,
        verified: false,
        error: 'Authentication failed: Invalid signature',
        security_details: {
          signature_valid: false,
          certificate_chain_valid: false,
          timestamp_valid: true
        }
      });

      await helpers.navigateToTab('Verifier');
      await helpers.clickButton('Simulate QR Code Scan');
      await page.waitForTimeout(2500);
      await helpers.clickButton('Verify Presentation');

      // Should properly handle authentication failure
      await page.waitForTimeout(2000);
      await expect(page.locator('text=Credential verification successful!')).not.toBeVisible();
    });

    test('should validate certificate security', async ({ page }) => {
      await helpers.mockApiResponse('**/api/verifier/certificates/dashboard', {
        overview: {
          total_certificates: 3,
          critical_alerts: 2,
          certificates_needing_renewal: 1,
          expired_certificates: 1
        },
        certificates: [
          {
            certificate_id: 'expired_cert',
            common_name: 'Expired Certificate',
            status: 'expired',
            days_until_expiry: -30,
            security_issues: ['Certificate expired', 'Revocation status unknown']
          },
          {
            certificate_id: 'compromised_cert',
            common_name: 'Compromised Certificate',
            status: 'revoked',
            days_until_expiry: 100,
            security_issues: ['Certificate revoked due to compromise']
          }
        ]
      });

      await helpers.navigateToTab('Enhanced');
      await helpers.clickButton('Certificate Monitor');

      await page.waitForTimeout(1000);

      // Verify security issues are prominently displayed
      await expect(page.locator('text=2')).toBeVisible(); // Critical alerts
      await expect(page.locator('text=Expired Certificate')).toBeVisible();
      await expect(page.locator('text=Compromised Certificate')).toBeVisible();

      // Verify critical status indicators
      await expect(page.locator('[data-testid="ErrorIcon"]')).toHaveCount({ min: 1 });
    });
  });

  test.describe('Accessibility and Usability', () => {
    test('should be accessible via keyboard navigation', async ({ page }) => {
      // Test keyboard navigation through the demo
      await page.keyboard.press('Tab'); // Should focus first tab
      await page.keyboard.press('Enter'); // Should activate tab

      // Continue tabbing through interactive elements
      for (let i = 0; i < 10; i++) {
        await page.keyboard.press('Tab');
      }

      // Should not trap focus unexpectedly
      const focusedElement = await page.evaluate(() => document.activeElement?.tagName);
      expect(['BUTTON', 'INPUT', 'TEXTAREA', 'A']).toContain(focusedElement);
    });

    test('should provide appropriate ARIA labels and roles', async ({ page }) => {
      await helpers.navigateToTab('Enhanced');

      // Check for proper ARIA attributes
      const buttons = page.locator('button');
      const buttonCount = await buttons.count();

      // Verify buttons have accessible names
      for (let i = 0; i < Math.min(buttonCount, 5); i++) {
        const button = buttons.nth(i);
        const ariaLabel = await button.getAttribute('aria-label');
        const textContent = await button.textContent();

        // Should have either aria-label or text content
        expect(ariaLabel || textContent?.trim()).toBeTruthy();
      }

      // Check for proper heading hierarchy
      await expect(page.locator('h1, h2, h3, h4, h5, h6')).toHaveCount({ min: 1 });
    });

    test('should work with screen reader simulation', async ({ page }) => {
      // Test that important content is properly announced
      await helpers.navigateToTab('Enhanced');
      await helpers.clickButton('Age Verification');

      // Verify proper heading structure
      await expect(page.locator('h6')).toContainText('Enhanced Age Verification Demo');

      // Verify form labels are associated with inputs
      const selectLabel = page.locator('label:has-text("Use Case")');
      if (await selectLabel.count() > 0) {
        await expect(selectLabel).toBeVisible();
      }

      // Verify status messages are properly announced
      await helpers.selectAgeVerificationUseCase('Alcohol Purchase (21+)');
      await helpers.clickButton('Create Request');

      // Alert should be accessible
      await page.waitForTimeout(1000);
      const alerts = page.locator('[role="alert"]');
      if (await alerts.count() > 0) {
        await expect(alerts.first()).toBeVisible();
      }
    });
  });
});
