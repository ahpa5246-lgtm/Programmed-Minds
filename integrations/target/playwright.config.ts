import { defineConfig } from '@playwright/test';

if (!process.env.BASE_URL) throw new Error('Set the explicitly owned BASE_URL');

export default defineConfig({
  testDir: './e2e',
  forbidOnly: true,
  retries: 0,
  use: { baseURL: process.env.BASE_URL, trace: 'off' },
});
