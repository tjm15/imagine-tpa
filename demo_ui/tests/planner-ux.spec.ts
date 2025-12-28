import { test, expect } from '@playwright/test';

test('Planner UX - Narrative Guide and Reasoning Tray', async ({ page }) => {
  // 1. Load the page
  await page.goto('/');
  
  // Click to enter the project
  await page.getByRole('button', { name: 'Open Plan Studio' }).click();
  
  // Wait for the header to appear (using specific class to distinguish from editor content)
  await expect(page.locator('h1.text-3xl')).toHaveText('Place Portrait: Baseline Evidence');
  
  // Take initial screenshot
  await page.screenshot({ path: 'test-results/screenshots/1-initial-load.png' });

  // 2. Verify Narrative Guide Toggle (Initially Open)
  const guideButton = page.getByRole('button', { name: 'Hide Guide' });
  await expect(guideButton).toBeVisible();
  
  // 3. Verify Narrative Guide Content
  // Baseline work should start at Evidence Curation.
  await expect(page.getByText('Evidence Curation')).toBeVisible();
  await expect(page.getByText('Gather facts required to assess the issues.')).toBeVisible();
  
  // Take screenshot with guide open
  await page.screenshot({ path: 'test-results/screenshots/2-guide-open.png' });

  // 4. Verify Reasoning Tray
  const trayHeader = page.getByText('Reasoning', { exact: true });
  await expect(trayHeader).toBeVisible();
  
  // 5. Expand Reasoning Tray
  await trayHeader.click();
  await expect(page.getByText('Considerations Ledger')).toBeVisible();
  
  // Take screenshot with tray open
  await page.screenshot({ path: 'test-results/screenshots/3-tray-open.png' });

  // Take screenshot with tray open
  await page.screenshot({ path: 'test-results/screenshots/3-tray-open.png' });
});
