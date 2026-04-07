import { test, expect } from '@playwright/test';

test.describe('Login', () => {
	test('shows login form when not authenticated', async ({ page }) => {
		await page.goto('/');
		await expect(page.getByRole('heading', { name: 'Claude Chat' })).toBeVisible();
		await expect(page.getByPlaceholder('you@example.com')).toBeVisible();
		await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible();
	});

	test('sidebar is not visible before login', async ({ page }) => {
		await page.goto('/');
		await expect(page.locator('aside.sidebar')).not.toBeVisible();
	});
});
