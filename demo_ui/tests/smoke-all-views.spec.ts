import { test, expect } from '@playwright/test';

test.describe('End-to-end demo smoke', () => {
  test('Plan project views render across document/map/scenarios/visuals', async ({ page }) => {
    await page.goto('/');

    // Enter Plan Studio
    await page.getByRole('button', { name: 'Open Plan Studio' }).click();

    // Document view baseline
    await expect(page.getByRole('heading', { name: 'Place Portrait: Baseline Evidence' }).first()).toBeVisible();
    await page.screenshot({ path: 'test-results/screenshots/4-plan-document.png', fullPage: true });

    // Switch to Map view
    await page.getByRole('button', { name: 'Map & Plans' }).click();
    await expect(page.getByRole('heading', { name: 'Strategic Map Canvas' })).toBeVisible();
    await expect(page.getByText('Draw to query, snapshot to cite')).toBeVisible();
    await page.screenshot({ path: 'test-results/screenshots/5-plan-map.png', fullPage: true });

    // Switch to Scenarios/Judgement view
    await page.getByRole('button', { name: 'Scenarios' }).click();
    // Check for strategic scenarios label and content
    await expect(page.getByText('Strategic Scenarios')).toBeVisible();
    await expect(page.getByText('Spatial Strategy Map')).toBeVisible();
    await page.screenshot({ path: 'test-results/screenshots/6-plan-scenarios.png', fullPage: true });

    // Switch to Visuals/Reality view
    await page.getByRole('button', { name: 'Visuals' }).click();
    await expect(page.getByRole('heading', { name: 'Visual Evidence & Overlays' })).toBeVisible();
    await expect(page.getByText('Visuospatial reasoning with plan-reality registration')).toBeVisible();
    await page.screenshot({ path: 'test-results/screenshots/7-plan-visuals.png', fullPage: true });
  });
});
