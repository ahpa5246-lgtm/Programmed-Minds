import { test, expect } from '@playwright/test';

// Replace these product assertions with the implemented application's contract.
// This example is intentionally a real check, rather than an always-pass fixture.
test('home page exposes a usable primary action', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Create project', exact: true })).toBeEnabled();
});
