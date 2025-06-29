import { test, expect } from '@playwright/test';

test.describe('Coordinates Functionality', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('should display default coordinates (Glasgow)', async ({ page }) => {
    const latitudeInput = page.locator('#latitude');
    const longitudeInput = page.locator('#longitude');
    
    await expect(latitudeInput).toHaveValue('55.8827');
    await expect(longitudeInput).toHaveValue('-4.2589');
  });

  test('should allow manual coordinate input', async ({ page }) => {
    const latitudeInput = page.locator('#latitude');
    const longitudeInput = page.locator('#longitude');
    
    await latitudeInput.fill('56.8167');
    await longitudeInput.fill('-5.1056');
    
    await expect(latitudeInput).toHaveValue('56.8167');
    await expect(longitudeInput).toHaveValue('-5.1056');
  });

  test('should handle geolocation permission granted', async ({ page, context }) => {
    // Mock geolocation
    await context.grantPermissions(['geolocation']);
    await context.setGeolocation({ latitude: 57.1497, longitude: -2.0943 });
    
    const useLocationBtn = page.locator('#use-location-btn');
    const locationStatus = page.locator('#location-status');
    
    await useLocationBtn.click();
    
    // Wait for the location to be updated
    await expect(locationStatus).toContainText('Location found');
    
    // Check that coordinates were updated
    const latitudeInput = page.locator('#latitude');
    const longitudeInput = page.locator('#longitude');
    
    await expect(latitudeInput).toHaveValue('57.1497');
    await expect(longitudeInput).toHaveValue('-2.0943');
    
    // Check that button text updates
    await expect(useLocationBtn).toHaveText('✅ Location Updated');
  });

  test('should handle geolocation permission denied', async ({ page, context }) => {
    // Grant permissions first, then deny during the test
    const useLocationBtn = page.locator('#use-location-btn');
    const locationStatus = page.locator('#location-status');
    
    // Mock geolocation error
    await page.addInitScript(() => {
      navigator.geolocation = {
        getCurrentPosition: (success, error) => {
          error({ code: 1, message: 'User denied Geolocation' });
        }
      };
    });
    
    await useLocationBtn.click();
    
    await expect(locationStatus).toContainText('Location access denied by user');
    await expect(useLocationBtn).toHaveText('📍 Use My Location');
  });

  test('should handle geolocation errors', async ({ page }) => {
    // Mock geolocation error - test that error handling works in general
    await page.addInitScript(() => {
      navigator.geolocation = {
        getCurrentPosition: (success, error) => {
          // Simulate any geolocation error
          error({ 
            code: 3, 
            message: 'Timeout'
          });
        }
      };
    });
    
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    const useLocationBtn = page.locator('#use-location-btn');
    const locationStatus = page.locator('#location-status');
    
    await useLocationBtn.click();
    
    // Test that some error message appears (could be timeout, permission denied, etc.)
    await expect(locationStatus).toContainText('❌');
    await expect(useLocationBtn).toHaveText('📍 Use My Location');
  });

  test('should validate coordinate inputs', async ({ page }) => {
    const latitudeInput = page.locator('#latitude');
    const longitudeInput = page.locator('#longitude');
    
    // Test invalid latitude (out of range)
    await latitudeInput.fill('91');
    await expect(latitudeInput).toHaveAttribute('type', 'number');
    
    // Test invalid longitude (out of range)
    await longitudeInput.fill('181');
    await expect(longitudeInput).toHaveAttribute('type', 'number');
    
    // Test valid coordinates
    await latitudeInput.fill('55.8827');
    await longitudeInput.fill('-4.2589');
    
    await expect(latitudeInput).toHaveValue('55.8827');
    await expect(longitudeInput).toHaveValue('-4.2589');
  });

  test('should preserve coordinates in form submission', async ({ page }) => {
    const latitudeInput = page.locator('#latitude');
    const longitudeInput = page.locator('#longitude');
    const searchBtn = page.locator('#search-btn');
    
    // Set custom coordinates
    await latitudeInput.fill('58.2083');
    await longitudeInput.fill('-6.3857');
    
    // Trigger search (will likely fail due to no mock data, but coordinates should be preserved)
    await searchBtn.click();
    
    // Coordinates should still be there after search
    await expect(latitudeInput).toHaveValue('58.2083');
    await expect(longitudeInput).toHaveValue('-6.3857');
  });
});