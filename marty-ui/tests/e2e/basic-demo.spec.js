const { test, expect } = require('@playwright/test');
const { DemoTestHelpers, mockCredentialData, mockApiResponses } = require('../utils/test-helpers');

// SKIPPED: These tests are for the OpenWallet Foundation mDoc/mDL Demo UI
// which has different navigation structure (Issuer/Verifier/Wallet/Enhanced tabs).
// The current app is "Marty Trust Services" with different tabs.
// Re-enable when the demo UI is integrated or these tests are updated.
test.describe.skip('Basic Demo Flow Tests', () => {
  let helpers;

  test.beforeEach(async ({ page }) => {
    helpers = new DemoTestHelpers(page);
    await page.goto('/');
    await helpers.waitForPageLoad();
  });

  test.describe('Navigation and UI', () => {
    test('should load home page and display main components', async ({ page }) => {
      // Verify home page loads
      await expect(page.locator('h1, h3')).toContainText('OpenWallet Foundation mDoc/mDL Demo');

      // Verify navigation tabs are present
      await expect(page.locator('[role="tablist"]')).toBeVisible();
      await expect(page.locator('text=Home')).toBeVisible();
      await expect(page.locator('text=Issuer')).toBeVisible();
      await expect(page.locator('text=Verifier')).toBeVisible();
      await expect(page.locator('text=Wallet')).toBeVisible();
      await expect(page.locator('text=Enhanced')).toBeVisible();

      // Verify core features are displayed
      await helpers.verifyCardContent('Core Demo Features', 'Credential Issuance');
      await helpers.verifyCardContent('Enhanced Features', 'Age Verification');
      await helpers.verifyCardContent('Technology Stack', 'OpenWallet Foundation');
    });

    test('should navigate between tabs successfully', async ({ page }) => {
      // Test navigation to each tab
      const tabs = ['Issuer', 'Verifier', 'Wallet', 'Enhanced'];

      for (const tab of tabs) {
        await helpers.navigateToTab(tab);

        // Verify URL or active tab state
        const activeTab = page.locator('[role="tab"][aria-selected="true"]');
        await expect(activeTab).toContainText(tab);

        // Verify tab content is loaded
        await expect(page.locator('h4, h5, h6')).toBeVisible();
      }

      // Navigate back to home
      await helpers.navigateToTab('Home');
      await expect(page.locator('h1, h3')).toContainText('OpenWallet Foundation mDoc/mDL Demo');
    });
  });

  test.describe('Issuer Service Tests', () => {
    test.beforeEach(async ({ page }) => {
      await helpers.navigateToTab('Issuer');
    });

    test('should display issuer demo interface', async ({ page }) => {
      await expect(page.locator('h4')).toContainText('Credential Issuer Demo');
      await expect(page.locator('text=Issue mobile driving license')).toBeVisible();

      // Verify stepper is present
      await expect(page.locator('.MuiStepper-root')).toBeVisible();
      await expect(page.locator('text=Enter Information')).toBeVisible();
      await expect(page.locator('text=Review Data')).toBeVisible();
      await expect(page.locator('text=Issue Credential')).toBeVisible();
    });

    test('should complete credential issuance flow', async ({ page }) => {
      // Mock the API response
      await helpers.mockApiResponse('**/api/issuer/issue', mockApiResponses.issuerSuccess);

      // Step 1: Enter Information
      await helpers.fillFormField('Given Name', mockCredentialData.given_name);
      await helpers.fillFormField('Family Name', mockCredentialData.family_name);
      await page.fill('input[type="date"]', mockCredentialData.birth_date);
      await helpers.fillFormField('Document Number', mockCredentialData.document_number);
      await helpers.fillFormField('Issuing Country', mockCredentialData.issuing_country);

      await helpers.clickButton('Next');

      // Step 2: Review Data
      await expect(page.locator('text=Review Credential Data')).toBeVisible();
      await expect(page.locator('text=GIVEN_NAME')).toBeVisible();
      await expect(page.locator(`text=${mockCredentialData.given_name}`)).toBeVisible();

      await helpers.clickButton('Next');

      // Step 3: Issue Credential
      await helpers.clickButton('Issue Credential');

      // Verify loading state
      await expect(page.locator('text=Issuing Credential...')).toBeVisible();

      // Wait for success
      await helpers.waitForAlert('success');
      await expect(page.locator('text=Credential issued successfully!')).toBeVisible();

      // Verify credential details are shown
      await helpers.verifyChipStatus('ID:', 'primary');
      await helpers.verifyChipStatus('Type:', 'secondary');
    });

    test('should handle form validation', async ({ page }) => {
      // Try to proceed without filling required fields
      await helpers.clickButton('Next');

      // Should still be on step 1 (form validation should prevent proceeding)
      await expect(page.locator('.MuiStep-root.Mui-active')).toContainText('Enter Information');
    });
  });

  test.describe('Verifier Service Tests', () => {
    test.beforeEach(async ({ page }) => {
      await helpers.navigateToTab('Verifier');
    });

    test('should display verifier demo interface', async ({ page }) => {
      await expect(page.locator('h4')).toContainText('Credential Verifier Demo');
      await expect(page.locator('text=Verify mobile driving license')).toBeVisible();

      // Verify capture and verify sections
      await helpers.verifyCardContent('1. Capture Presentation', 'Simulate QR Code Scan');
      await helpers.verifyCardContent('2. Verify Credential', 'Verify Presentation');
    });

    test('should simulate QR code scanning', async ({ page }) => {
      // Click simulate QR scan
      await helpers.clickButton('Simulate QR Code Scan');

      // Verify loading state
      await expect(page.locator('text=Scanning QR Code...')).toBeVisible();

      // Wait for scan completion and data to appear
      await page.waitForTimeout(2500); // Wait for simulation

      // Verify presentation data is populated
      const textarea = page.locator('textarea[placeholder*="presentation"]');
      await expect(textarea).not.toBeEmpty();

      // Verify accordion is present
      await expect(page.locator('text=Presentation Data')).toBeVisible();
    });

    test('should complete verification flow', async ({ page }) => {
      // Mock the API response
      await helpers.mockApiResponse('**/api/verifier/verify', mockApiResponses.verifierSuccess);

      // First simulate QR scan to get presentation data
      await helpers.clickButton('Simulate QR Code Scan');
      await page.waitForTimeout(2500);

      // Now verify the presentation
      await helpers.clickButton('Verify Presentation');

      // Verify loading state
      await expect(page.locator('text=Verifying...')).toBeVisible();

      // Wait for verification result
      await helpers.waitForAlert('success');

      // Verify success message and status
      await helpers.verifyChipStatus('VERIFIED', 'success');
      await expect(page.locator('text=Credential verification successful!')).toBeVisible();

      // Verify verification checks are shown
      await expect(page.locator('text=Verification Checks')).toBeVisible();
      await helpers.expandAccordion('Verification Checks');
      await expect(page.locator('text=Signature Verification')).toBeVisible();
    });

    test('should allow manual presentation input', async ({ page }) => {
      const mockPresentation = JSON.stringify({
        "@context": ["https://www.w3.org/2018/credentials/v1"],
        "type": ["VerifiablePresentation"]
      }, null, 2);

      // Fill presentation data manually
      await page.fill('textarea[placeholder*="presentation"]', mockPresentation);

      // Verify verify button becomes enabled
      const verifyButton = page.locator('button:has-text("Verify Presentation")');
      await expect(verifyButton).toBeEnabled();
    });
  });

  test.describe('Wallet Service Tests', () => {
    test.beforeEach(async ({ page }) => {
      await helpers.navigateToTab('Wallet');
    });

    test('should display wallet demo interface', async ({ page }) => {
      await expect(page.locator('h4')).toContainText('Digital Wallet Demo');
      await expect(page.locator('text=Manage your mobile driving license')).toBeVisible();

      // Verify action buttons
      await expect(page.locator('button:has-text("Add Demo Credential")')).toBeVisible();
      await expect(page.locator('button:has-text("Refresh Wallet")')).toBeVisible();
    });

    test('should display existing credentials', async ({ page }) => {
      // The wallet should show mock credentials
      await expect(page.locator('.MuiCard-root')).toHaveCount({ min: 1 });

      // Verify credential cards contain expected information
      await expect(page.locator('text=mDL')).toBeVisible();
      await expect(page.locator('text=Demo DMV')).toBeVisible();

      // Verify action buttons on credential cards
      await expect(page.locator('button:has-text("View")')).toBeVisible();
      await expect(page.locator('button:has-text("Share")')).toBeVisible();
      await expect(page.locator('button:has-text("Delete")')).toBeVisible();
    });

    test('should add new demo credential', async ({ page }) => {
      const initialCards = await page.locator('.MuiCard-root').count();

      // Click add demo credential
      await helpers.clickButton('Add Demo Credential');

      // Verify new credential was added
      await page.waitForTimeout(1000); // Allow time for UI update
      const newCards = await page.locator('.MuiCard-root').count();
      expect(newCards).toBeGreaterThan(initialCards);
    });

    test('should view credential details', async ({ page }) => {
      // Click view on first credential
      await page.locator('button:has-text("View")').first().click();

      // Verify dialog opens
      await expect(page.locator('[role="dialog"]')).toBeVisible();
      await expect(page.locator('text=Credential Details')).toBeVisible();

      // Verify credential information is displayed
      await expect(page.locator('text=Type')).toBeVisible();
      await expect(page.locator('text=Status')).toBeVisible();
      await expect(page.locator('text=Subject Data')).toBeVisible();

      // Close dialog
      await helpers.clickButton('Close');
      await expect(page.locator('[role="dialog"]')).not.toBeVisible();
    });

    test('should open share credential dialog', async ({ page }) => {
      // Click share on first credential
      await page.locator('button:has-text("Share")').first().click();

      // Verify share dialog opens
      await expect(page.locator('[role="dialog"]')).toBeVisible();
      await expect(page.locator('text=Create Presentation')).toBeVisible();

      // Verify presentation request field
      await expect(page.locator('textarea[label*="Presentation Request"]')).toBeVisible();

      // Verify create button is disabled without input
      const createButton = page.locator('button:has-text("Create Presentation")');
      await expect(createButton).toBeDisabled();

      // Close dialog
      await helpers.clickButton('Cancel');
    });

    test('should delete credential', async ({ page }) => {
      const initialCards = await page.locator('.MuiCard-root').count();

      // Mock the confirm dialog
      page.on('dialog', dialog => dialog.accept());

      // Click delete on last credential
      await page.locator('button:has-text("Delete")').last().click();

      // Verify credential was removed
      await page.waitForTimeout(1000);
      const newCards = await page.locator('.MuiCard-root').count();
      expect(newCards).toBeLessThan(initialCards);
    });
  });

  test.describe('Responsive Design Tests', () => {
    test('should work on mobile viewport', async ({ page }) => {
      // Set mobile viewport
      await page.setViewportSize({ width: 375, height: 667 });

      await page.goto('/');
      await helpers.waitForPageLoad();

      // Verify main elements are still visible and accessible
      await expect(page.locator('h1, h3')).toBeVisible();
      await expect(page.locator('[role="tablist"]')).toBeVisible();

      // Test navigation on mobile
      await helpers.navigateToTab('Issuer');
      await expect(page.locator('h4')).toContainText('Credential Issuer Demo');
    });

    test('should work on tablet viewport', async ({ page }) => {
      // Set tablet viewport
      await page.setViewportSize({ width: 768, height: 1024 });

      await page.goto('/');
      await helpers.waitForPageLoad();

      // Verify layout adapts properly
      await expect(page.locator('h1, h3')).toBeVisible();
      await helpers.verifyCardContent('Core Demo Features', 'Credential Issuance');
    });
  });
});
