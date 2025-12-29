import { test, expect } from '@playwright/test';

test.describe('End-to-end demo smoke', () => {
  test('Plan project views render across document/map/scenarios/visuals', async ({ page }) => {
    await page.goto('/');

    // Enter Plan Studio
    await page.getByRole('button', { name: 'Open Plan Studio' }).click();

    // Studio mode - document with embedded figures
    await expect(page.getByRole('heading', { name: 'Place Portrait: Baseline Evidence' }).first()).toBeVisible();
    // Should show embedded figure placeholders
    await expect(page.getByText('Figure 1', { exact: false })).toBeVisible();
    await page.screenshot({ path: 'test-results/screenshots/4-plan-studio.png', fullPage: true });

    // Switch to Strategy mode - unified spatial workspace
    await page.getByRole('button', { name: 'Strategy' }).click();
    await expect(page.getByText('Strategic Scenarios')).toBeVisible();
    // Should show scenario bar and map
    await expect(page.getByText('Baseline 2024')).toBeVisible();
    await expect(page.getByText('Scenario A')).toBeVisible();
    await page.screenshot({ path: 'test-results/screenshots/5-plan-strategy.png', fullPage: true });
  });
});
