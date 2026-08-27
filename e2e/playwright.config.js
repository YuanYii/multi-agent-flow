const { defineConfig } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

let baseURL = 'http://127.0.0.1:32990';
try {
  const cfg = JSON.parse(fs.readFileSync(path.resolve(__dirname, '.runtime/config.json'), 'utf-8'));
  baseURL = cfg.baseURL;
} catch (e) { /* setup 前 */ }

module.exports = defineConfig({
  testDir: '.',
  globalSetup: require.resolve('./global-setup.js'),
  globalTeardown: require.resolve('./global-teardown.js'),
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    // 优先 runner 预装 Chrome;不可用时回落 Playwright 托管 Chromium(CI 显式安装)
    ...(process.env.CI ? {} : { channel: 'chrome' }),
    headless: true,
    viewport: { width: 1440, height: 900 },
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
    baseURL,
  },
});
