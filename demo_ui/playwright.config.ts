import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [['html', { open: 'never' }]],
  use: {
    baseURL: 'http://localhost:8086',
    trace: 'on-first-retry',
    screenshot: 'on',
  },
  projects: [
    {
      name: 'chromium',
      use: { 
        ...devices['Desktop Chrome'],
        channel: 'chrome', // Use installed Google Chrome
        viewport: { width: 1600, height: 900 },
        deviceScaleFactor: 2,
      },
    },
  ],
  /*
  webServer: {
    command: 'cd build && python3 -m http.server 5173',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000,
  },
  */
});
