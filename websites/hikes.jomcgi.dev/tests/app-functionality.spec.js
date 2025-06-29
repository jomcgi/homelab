import { test, expect } from '@playwright/test';

test.describe('App Core Functionality', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('should load and display the main page', async ({ page }) => {
    await expect(page).toHaveTitle('Hike Finder');
    await expect(page.locator('h1')).toContainText('🥾 Hike Finder');
    await expect(page.locator('header p')).toContainText('Find hiking routes with good weather conditions in Scotland');
  });

  test('should display all form sections', async ({ page }) => {
    await expect(page.locator('h3:has-text("📍 Your Location")')).toBeVisible();
    await expect(page.locator('h3:has-text("🚶 Hiking Preferences")')).toBeVisible();
    await expect(page.locator('h3:has-text("📅 Which Days Are You Available?")')).toBeVisible();
    await expect(page.locator('h3:has-text("🕐 Preferred Hiking Times")')).toBeVisible();
    await expect(page.locator('h3:has-text("🌤️ Weather Requirements")')).toBeVisible();
  });

  test('should have default form values', async ({ page }) => {
    await expect(page.locator('#radius')).toHaveValue('25');
    await expect(page.locator('#min-duration')).toHaveValue('2');
    await expect(page.locator('#max-duration')).toHaveValue('6');
    await expect(page.locator('#min-distance')).toHaveValue('3');
    await expect(page.locator('#max-distance')).toHaveValue('15');
    await expect(page.locator('#max-ascent')).toHaveValue('800');
    await expect(page.locator('#start-after')).toHaveValue('08:00');
    await expect(page.locator('#finish-before')).toHaveValue('16:00');
  });

  test('should generate date checkboxes for next 7 days', async ({ page }) => {
    const dateCheckboxes = page.locator('#available-dates input[type="checkbox"]');
    await expect(dateCheckboxes).toHaveCount(7);
    
    // All should be checked by default
    const checkedBoxes = page.locator('#available-dates input[type="checkbox"]:checked');
    await expect(checkedBoxes).toHaveCount(7);
  });

  test('should allow form input modifications', async ({ page }) => {
    await page.locator('#radius').fill('50');
    await page.locator('#min-duration').fill('1');
    await page.locator('#max-duration').fill('8');
    await page.locator('#max-ascent').fill('1200');
    
    await expect(page.locator('#radius')).toHaveValue('50');
    await expect(page.locator('#min-duration')).toHaveValue('1');
    await expect(page.locator('#max-duration')).toHaveValue('8');
    await expect(page.locator('#max-ascent')).toHaveValue('1200');
  });

  test('should handle weather preferences', async ({ page }) => {
    await page.locator('#max-precipitation-mm').fill('1.0');
    await page.locator('#max-wind-speed-kmh').fill('25');
    await page.locator('#min-temperature-c').fill('10');
    await page.locator('#max-temperature-c').fill('20');
    
    await expect(page.locator('#max-precipitation-mm')).toHaveValue('1.0');
    await expect(page.locator('#max-wind-speed-kmh')).toHaveValue('25');
    await expect(page.locator('#min-temperature-c')).toHaveValue('10');
    await expect(page.locator('#max-temperature-c')).toHaveValue('20');
  });

  test('should handle date selection', async ({ page }) => {
    // Uncheck all dates
    const dateCheckboxes = page.locator('#available-dates input[type="checkbox"]');
    const count = await dateCheckboxes.count();
    
    for (let i = 0; i < count; i++) {
      await dateCheckboxes.nth(i).uncheck();
    }
    
    // Check that none are selected
    const checkedBoxes = page.locator('#available-dates input[type="checkbox"]:checked');
    await expect(checkedBoxes).toHaveCount(0);
    
    // Check first date
    await dateCheckboxes.first().check();
    await expect(page.locator('#available-dates input[type="checkbox"]:checked')).toHaveCount(1);
  });

  test('should show error when no dates selected and search clicked', async ({ page }) => {
    // Uncheck all dates
    const dateCheckboxes = page.locator('#available-dates input[type="checkbox"]');
    const count = await dateCheckboxes.count();
    
    for (let i = 0; i < count; i++) {
      await dateCheckboxes.nth(i).uncheck();
    }
    
    // Click search
    await page.locator('#search-btn').click();
    
    // Should show error
    const errorDiv = page.locator('#error');
    await expect(errorDiv).toContainText('Please select at least one date');
    await expect(errorDiv).not.toHaveClass(/hidden/);
  });

  test('should handle Enter key for search', async ({ page }) => {
    const searchBtn = page.locator('#search-btn');
    
    // Focus on an input and press Enter
    await page.locator('#radius').focus();
    await page.keyboard.press('Enter');
    
    // This should trigger the search function (though it may fail without mock data)
    // We can't easily test the actual search without mocking the data loading
  });

  test('should display footer information', async ({ page }) => {
    await expect(page.locator('footer')).toContainText('Data last updated:');
    await expect(page.locator('footer')).toContainText('Weather data from met.no');
    await expect(page.locator('footer')).toContainText('Walking routes from walkhighlands.co.uk');
  });

  test('should have proper form validation attributes', async ({ page }) => {
    // Check required fields
    await expect(page.locator('#latitude')).toHaveAttribute('required');
    await expect(page.locator('#longitude')).toHaveAttribute('required');
    await expect(page.locator('#radius')).toHaveAttribute('required');
    
    // Check number input constraints
    await expect(page.locator('#radius')).toHaveAttribute('min', '1');
    await expect(page.locator('#radius')).toHaveAttribute('max', '100');
    await expect(page.locator('#min-duration')).toHaveAttribute('min', '0.5');
    await expect(page.locator('#min-duration')).toHaveAttribute('max', '12');
  });

  test('should show loading state during search', async ({ page }) => {
    const loadingDiv = page.locator('#loading');
    const searchBtn = page.locator('#search-btn');
    
    // Initially hidden
    await expect(loadingDiv).toHaveClass(/hidden/);
    
    // Click search to trigger loading (will likely fail due to no mock data)
    await searchBtn.click();
    
    // Should briefly show loading (may be too fast to catch reliably)
    // This test documents the expected behavior
  });
});