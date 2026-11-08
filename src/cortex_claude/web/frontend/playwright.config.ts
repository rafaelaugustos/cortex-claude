import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './tests', workers: 1, timeout: 30000,
  use: { baseURL: 'http://127.0.0.1:37813', channel: process.env.CI ? undefined : 'chrome', viewport: { width: 1440, height: 1050 }, trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: { command: '../../../../.venv/bin/python ../../../../scripts/dashboard_fixture.py --port 37813', url: 'http://127.0.0.1:37813/api/learning', reuseExistingServer: false, timeout: 30000 },
})
