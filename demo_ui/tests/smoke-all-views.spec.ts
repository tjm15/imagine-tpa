import { test, expect } from '@playwright/test';

test.describe('End-to-end demo smoke', () => {
  test('Plan project views render across document/map/scenarios/visuals', async ({ page }) => {
    await page.setViewportSize({ width: 1400, height: 700 });
    await page.goto('/');

    // Enter Plan Studio
    await page.getByRole('button', { name: 'Open Plan Studio' }).click();

    // Studio mode - document with embedded figures
    await expect(page.getByRole('heading', { name: 'Place Portrait: Baseline Evidence' }).first()).toBeVisible();
    // Should show embedded figure placeholders
    await expect(page.getByText('Figure 1', { exact: false })).toBeVisible();

    // Studio scroll contract: the middle pane owns exactly one scroll container.
    const studioScroll = page.getByTestId('studio-scroll');
    await expect(studioScroll).toBeVisible();
    const studioOverflowY = await studioScroll.evaluate((el) => getComputedStyle(el).overflowY);
    expect(['auto', 'scroll']).toContain(studioOverflowY);
    const studioScrolled = await studioScroll.evaluate((el) => {
      el.scrollTop = 600;
      return el.scrollTop;
    });
    expect(studioScrolled).toBeGreaterThan(0);
    // Header should remain visible after scrolling.
    await expect(page.getByRole('heading', { name: 'Place Portrait: Baseline Evidence' }).first()).toBeVisible();

    await page.screenshot({ path: 'test-results/screenshots/4-plan-studio.png', fullPage: true });

    // Switch to Strategy mode - unified spatial workspace
    await page.getByRole('button', { name: 'Strategy' }).click();
    await expect(page.getByText('Strategic Scenarios')).toBeVisible();
    // Should show scenario bar and map
    await expect(page.getByText('Baseline 2024')).toBeVisible();
    await expect(page.getByText('Scenario A')).toBeVisible();

    // Strategy scroll contract: the central canvas scrolls; the scenario bar stays put.
    const strategyScroll = page.getByTestId('strategy-scroll');
    await expect(strategyScroll).toBeVisible();
    const strategyOverflowY = await strategyScroll.evaluate((el) => getComputedStyle(el).overflowY);
    expect(['auto', 'scroll']).toContain(strategyOverflowY);
    const strategyScrolled = await strategyScroll.evaluate((el) => {
      el.scrollTop = 800;
      return el.scrollTop;
    });
    expect(strategyScrolled).toBeGreaterThan(0);
    await expect(page.getByText('Baseline 2024')).toBeVisible();

    await page.screenshot({ path: 'test-results/screenshots/5-plan-strategy.png', fullPage: true });
  });
});
