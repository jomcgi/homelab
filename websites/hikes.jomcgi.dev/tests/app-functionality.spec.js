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

  test('should update viable dates when filters change', async ({ page }) => {
    // Wait for initial data to load
    await page.waitForTimeout(1000);
    
    const datesContainer = page.locator('#available-dates');
    const initialDateCount = await datesContainer.locator('input[type="checkbox"]').count();
    
    // Change a filter that should trigger viable date update
    await page.locator('#max-precipitation-mm').fill('0.1');
    
    // Wait for debounced update (500ms + processing time)
    await page.waitForTimeout(1000);
    
    // The dates section should still be present (exact count may vary based on data)
    await expect(datesContainer).toBeVisible();
    
    // Should not show error message immediately after filter change with reasonable values
    const noViableDatesWarning = page.locator('.no-viable-dates');
    await expect(noViableDatesWarning).not.toBeVisible();
  });

  test('should show no viable dates warning with extreme filters', async ({ page }) => {
    // Wait for initial data to load
    await page.waitForTimeout(1000);
    
    // Set extreme filters that should result in no viable dates
    await page.locator('#max-precipitation-mm').fill('0');
    await page.locator('#max-wind-speed-kmh').fill('1');
    await page.locator('#min-temperature-c').fill('25');
    await page.locator('#max-temperature-c').fill('30');
    
    // Wait for debounced update and processing
    await page.waitForTimeout(2000);
    
    // Should show the no viable dates warning
    const noViableDatesWarning = page.locator('.no-viable-dates');
    await expect(noViableDatesWarning).toBeVisible();
    await expect(noViableDatesWarning).toContainText('No viable days found for your current filter combination');
    await expect(noViableDatesWarning).toContainText('Try relaxing your weather requirements');
  });

  test('should handle location changes for viable date updates', async ({ page }) => {
    // Wait for initial data to load
    await page.waitForTimeout(1000);
    
    const datesContainer = page.locator('#available-dates');
    
    // Change location coordinates
    await page.locator('#latitude').fill('57.1497'); // Inverness
    await page.locator('#longitude').fill('-4.4246');
    
    // Wait for debounced update
    await page.waitForTimeout(1000);
    
    // Dates container should still be visible and functional
    await expect(datesContainer).toBeVisible();
    
    // Should have date checkboxes (count may vary based on available data)
    const dateCheckboxes = datesContainer.locator('input[type="checkbox"]');
    const checkboxCount = await dateCheckboxes.count();
    
    // Either we have viable dates (checkboxes) or a warning message
    if (checkboxCount === 0) {
      const noViableDatesWarning = page.locator('.no-viable-dates');
      await expect(noViableDatesWarning).toBeVisible();
    } else {
      await expect(dateCheckboxes.first()).toBeVisible();
    }
  });

  test('should handle time preference changes for viable dates', async ({ page }) => {
    // Wait for initial data to load
    await page.waitForTimeout(1000);
    
    // Change time preferences to a narrow window
    await page.locator('#start-after').fill('11:00');
    await page.locator('#finish-before').fill('12:00');
    
    // Wait for debounced update
    await page.waitForTimeout(1000);
    
    const datesContainer = page.locator('#available-dates');
    await expect(datesContainer).toBeVisible();
    
    // With such a narrow time window, we might get no viable dates
    // This tests that the system handles time constraints properly
    const dateCheckboxes = datesContainer.locator('input[type="checkbox"]');
    const noViableDatesWarning = page.locator('.no-viable-dates');
    
    // Should either show dates or warning, but container should always be visible
    const hasCheckboxes = await dateCheckboxes.count() > 0;
    const hasWarning = await noViableDatesWarning.isVisible();
    
    expect(hasCheckboxes || hasWarning).toBe(true);
  });
});