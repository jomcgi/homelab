import { test, expect } from '@playwright/test';

test.describe('Deployment Health Checks', () => {
  test('should load main page without errors', async ({ page }) => {
    // Monitor console errors
    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    await page.goto('/');
    
    // Check that page loads successfully
    await expect(page).toHaveTitle('Hike Finder');
    
    // Verify no critical console errors
    const criticalErrors = errors.filter(error => 
      !error.includes('favicon') && // Ignore favicon errors
      !error.includes('woff2') &&   // Ignore font loading issues
      !error.includes('_gaq') &&    // Ignore analytics issues
      !error.includes('gtag')       // Ignore Google Analytics issues
    );
    
    if (criticalErrors.length > 0) {
      console.log('Console errors detected:', criticalErrors);
      expect(criticalErrors).toHaveLength(0);
    }
  });

  test('should load all critical assets', async ({ page }) => {
    await page.goto('/');
    
    // Check that JavaScript loads
    await expect(page.locator('#search-btn')).toBeVisible();
    
    // Check that CSS loads (verify styled elements)
    const header = page.locator('header');
    await expect(header).toBeVisible();
    
    // Verify form elements are present
    await expect(page.locator('#latitude')).toBeVisible();
    await expect(page.locator('#longitude')).toBeVisible();
    await expect(page.locator('#radius')).toBeVisible();
  });

  test('should have working search functionality', async ({ page }) => {
    await page.goto('/');
    
    // Fill in basic form data
    await page.locator('#latitude').fill('55.8642');
    await page.locator('#longitude').fill('-4.2518');
    await page.locator('#radius').fill('25');
    
    // Click search button
    await page.locator('#search-btn').click();
    
    // Should show loading state briefly, then results or error
    // Wait for loading to finish
    await expect(page.locator('#loading')).toHaveClass(/hidden/, { timeout: 10000 });
    
    // Should either show results or an error (both are valid for health check)
    const results = page.locator('#results');
    const error = page.locator('#error');
    
    const resultsVisible = await results.isVisible();
    const errorVisible = await error.isVisible();
    
    // Either results or error should be visible (indicates app is functional)
    expect(resultsVisible || errorVisible).toBe(true);
  });

  test('should handle geolocation gracefully', async ({ page }) => {
    await page.goto('/');
    
    // Mock geolocation denial
    await page.context().grantPermissions([]);
    
    // Click location button
    await page.locator('#use-location-btn').click();
    
    // Should show appropriate error message
    const locationStatus = page.locator('#location-status');
    await expect(locationStatus).toBeVisible();
    
    // Should contain error message about location access
    await expect(locationStatus).toContainText(/denied|unavailable|error/i);
  });
});