/**
 * Travel Document Application Flow Tests
 * 
 * Tests for the full applicant journey: login, application submission,
 * document upload, status tracking, and approval notification.
 * 
 * SKIPPED: Applicant dashboard UI not yet implemented - shows Internal Server Error
 */
const { test, expect } = require('@playwright/test');
const { 
  AuthHelpers, 
  PushNotificationHelpers,
  EmailTestHelpers,
  SEEDED_USERS 
} = require('../../utils/test-helpers');

test.describe.skip('Applicant Login and Dashboard', () => {
  let auth;

  test.beforeEach(async ({ page }) => {
    auth = new AuthHelpers(page);
    await page.goto('/');
  });

  test('seeded applicant can login successfully', async ({ page }) => {
    await auth.loginAsSeededUser('applicant1');
    
    // Should reach applicant dashboard
    await expect(page).toHaveURL(/\/(dashboard|applications|home)/);
    
    // Should see applicant-specific content
    await expect(page.locator('body')).toContainText(
      SEEDED_USERS.applicant1.firstName
    );
  });

  test('applicant sees their applications', async ({ page }) => {
    await auth.loginAsSeededUser('applicant1');
    
    // Navigate to applications
    await page.click('text=Applications, text=My Applications');
    
    // Should see applications list or empty state
    await expect(
      page.locator('table, .MuiList-root')
        .or(page.locator('text=No applications'))
        .or(page.locator('button:has-text("New Application")'))
    ).toBeVisible();
  });

  test('applicant can view their profile', async ({ page }) => {
    await auth.loginAsSeededUser('applicant1');
    
    // Navigate to profile
    await page.click('[data-testid="user-menu"], .MuiAvatar-root, text=Profile');
    await page.click('text=Profile, text=Account');
    
    // Should see profile information
    await expect(page.locator('body')).toContainText(SEEDED_USERS.applicant1.email);
    await expect(page.locator('body')).toContainText(SEEDED_USERS.applicant1.firstName);
  });
});

test.describe.skip('Travel Document Application', () => {
  let auth;
  let pushNotifications;
  let emailHelper;

  test.beforeEach(async ({ page }) => {
    auth = new AuthHelpers(page);
    pushNotifications = new PushNotificationHelpers(page);
    emailHelper = new EmailTestHelpers(page);
    
    await page.goto('/');
    await auth.loginAsSeededUser('applicant1');
    
    // Clear notifications and emails for clean test
    await pushNotifications.clearAllNotifications();
    await emailHelper.clearAllEmails();
  });

  test('applicant can start new travel document application', async ({ page }) => {
    // Navigate to applications
    await page.click('text=Applications, text=Apply');
    
    // Click new application
    await page.click('button:has-text("New Application"), button:has-text("Apply"), button:has-text("Start")');
    
    // Should see application form
    await expect(page.locator('text=Travel Document, text=Application Form')).toBeVisible();
    
    // Should see document type selection
    await expect(
      page.locator('text=Passport')
        .or(page.locator('text=Digital Travel Credential'))
        .or(page.locator('text=Document Type'))
    ).toBeVisible();
  });

  test('applicant can complete application form', async ({ page }) => {
    await page.click('text=Applications');
    await page.click('button:has-text("New Application")');
    
    // Step 1: Select document type
    await page.click('text=Digital Travel Credential, text=DTC');
    await page.click('button:has-text("Next"), button:has-text("Continue")');
    
    // Step 2: Personal information (may be pre-filled from profile)
    await page.waitForSelector('input[name="firstName"], input[name="givenName"]');
    
    // Verify pre-filled data
    const firstName = await page.inputValue('input[name="firstName"], input[name="givenName"]');
    expect(firstName).toBe(SEEDED_USERS.applicant1.firstName);
    
    // Fill additional required fields
    await page.fill('input[name="nationality"]', SEEDED_USERS.applicant1.nationality);
    await page.fill('input[name="dateOfBirth"]', SEEDED_USERS.applicant1.dateOfBirth);
    
    await page.click('button:has-text("Next")');
    
    // Step 3: Document upload
    await page.waitForSelector('input[type="file"], text=Upload');
    
    // Upload photo (using test fixture)
    const photoInput = page.locator('input[type="file"][accept*="image"]').first();
    await photoInput.setInputFiles({
      name: 'photo.jpg',
      mimeType: 'image/jpeg',
      buffer: Buffer.from('fake-image-data'),
    });
    
    await page.click('button:has-text("Next")');
    
    // Step 4: Review and submit
    await page.waitForSelector('text=Review, text=Confirm');
    
    // Verify summary
    await expect(page.locator('body')).toContainText(SEEDED_USERS.applicant1.firstName);
    await expect(page.locator('body')).toContainText('Digital Travel Credential');
    
    // Accept terms if present
    const termsCheckbox = page.locator('input[name="acceptTerms"], label:has-text("I agree")');
    if (await termsCheckbox.isVisible()) {
      await termsCheckbox.click();
    }
    
    // Submit application
    await page.click('button:has-text("Submit"), button:has-text("Apply")');
    
    // Should see success message
    await expect(page.locator('.MuiAlert-success, text=Application Submitted')).toBeVisible();
  });

  test('applicant can track application status', async ({ page }) => {
    // Assume application already exists
    await page.click('text=Applications');
    
    // Click on an application
    await page.click('tr:first-child, .MuiListItem-root:first-child');
    
    // Should see status information
    await expect(
      page.locator('text=Pending')
        .or(page.locator('text=In Review'))
        .or(page.locator('text=Approved'))
        .or(page.locator('text=Status'))
    ).toBeVisible();
    
    // Should see timeline or status history
    await expect(
      page.locator('.MuiTimeline-root')
        .or(page.locator('text=Submitted'))
        .or(page.locator('[data-testid="status-timeline"]'))
    ).toBeVisible();
  });

  test('applicant can upload additional documents', async ({ page }) => {
    await page.click('text=Applications');
    await page.click('tr:first-child');
    
    // Find upload section
    await page.click('text=Documents, text=Uploads');
    
    // Upload additional document
    const uploadButton = page.locator('button:has-text("Upload"), button:has-text("Add Document")');
    if (await uploadButton.isVisible()) {
      await uploadButton.click();
      
      const fileInput = page.locator('input[type="file"]').first();
      await fileInput.setInputFiles({
        name: 'supporting-doc.pdf',
        mimeType: 'application/pdf',
        buffer: Buffer.from('fake-pdf-data'),
      });
      
      await page.click('button:has-text("Upload"), button:has-text("Submit")');
      
      await expect(page.locator('text=supporting-doc')).toBeVisible();
    }
  });

  test('applicant receives notification on status change', async ({ page }) => {
    // First submit an application
    await page.click('text=Applications');
    await page.click('button:has-text("New Application")');
    await page.click('text=Digital Travel Credential');
    await page.click('button:has-text("Next")');
    await page.click('button:has-text("Next")');
    await page.click('button:has-text("Next")');
    await page.click('button:has-text("Submit")');
    
    // Wait for submission notification
    const notification = await pushNotifications.waitForNotification('application.submitted', 15000);
    expect(notification).toBeTruthy();
    expect(notification.event_type).toBe('application.submitted');
  });

  test('applicant can cancel pending application', async ({ page }) => {
    await page.click('text=Applications');
    
    // Find pending application
    const pendingRow = page.locator('tr:has-text("Pending")').first();
    if (await pendingRow.isVisible()) {
      await pendingRow.click();
      
      // Cancel application
      await page.click('button:has-text("Cancel"), button:has-text("Withdraw")');
      
      // Confirm cancellation
      await page.click('button:has-text("Confirm"), button:has-text("Yes")');
      
      // Status should change
      await expect(page.locator('text=Cancelled, text=Withdrawn')).toBeVisible();
    }
  });
});

test.describe.skip('Application Validation', () => {
  let auth;

  test.beforeEach(async ({ page }) => {
    auth = new AuthHelpers(page);
    await page.goto('/');
    await auth.loginAsSeededUser('applicant1');
  });

  test('form validation prevents incomplete submission', async ({ page }) => {
    await page.click('text=Applications');
    await page.click('button:has-text("New Application")');
    
    // Skip to end without filling required fields
    await page.click('text=Digital Travel Credential');
    await page.click('button:has-text("Next")');
    
    // Clear a required field
    await page.fill('input[name="firstName"]', '');
    
    // Try to proceed
    await page.click('button:has-text("Next")');
    
    // Should see validation error
    await expect(page.locator('.MuiFormHelperText-error, text=required')).toBeVisible();
  });

  test('file upload validates file types', async ({ page }) => {
    await page.click('text=Applications');
    await page.click('button:has-text("New Application")');
    await page.click('text=Digital Travel Credential');
    await page.click('button:has-text("Next")');
    await page.click('button:has-text("Next")');
    
    // Try to upload invalid file type
    const photoInput = page.locator('input[type="file"][accept*="image"]').first();
    await photoInput.setInputFiles({
      name: 'invalid.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('not an image'),
    });
    
    // Should see error about file type
    await expect(
      page.locator('text=Invalid file type, text=Please upload an image')
    ).toBeVisible();
  });
});
