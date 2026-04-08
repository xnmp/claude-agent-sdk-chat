import { test, expect } from '@playwright/test';

/**
 * E2E tests for the full conversation lifecycle.
 * Requires both backend (port 8000) and frontend (port 5173) running.
 *
 * Tests are written to be robust against pre-existing data — they
 * track counts relative to the initial state rather than assuming empty.
 */

test.describe('Conversation lifecycle', () => {
	test.describe.configure({ mode: 'serial' });

	test.beforeEach(async ({ page }) => {
		// Clear localStorage before navigation to avoid auto-login from stale data
		await page.addInitScript(() => localStorage.clear());
		await page.goto('/');
		await page.waitForLoadState('networkidle');

		// Fill login form and submit
		await page.getByPlaceholder('you@example.com').fill('e2e-test@example.com');
		await page.getByPlaceholder('Your name').fill('E2E Tester');
		await page.getByRole('button', { name: /sign in/i }).click();

		// Wait for sidebar to appear (login complete — requires backend API call to succeed)
		await expect(page.locator('aside.sidebar')).toBeVisible({ timeout: 10000 });
	});

	test('login shows sidebar with user info', async ({ page }) => {
		await expect(page.locator('.user-name')).toHaveText('E2E Tester');
		await expect(page.locator('.conversation-list')).toBeVisible();
	});

	test('create conversation increases sidebar count', async ({ page }) => {
		const initialCount = await page.locator('.conversation-item').count();

		await page.getByRole('button', { name: 'New', exact: true }).click();

		await expect(page.locator('.conversation-item')).toHaveCount(initialCount + 1);
		// The newest conversation should be first and untitled
		await expect(page.locator('.conv-title').first()).toHaveText('New conversation');
	});

	test('selecting conversation shows chat view', async ({ page }) => {
		await page.getByRole('button', { name: 'New', exact: true }).click();

		// Click the first (newest) conversation
		await page.locator('.conversation-item').first().click();

		await expect(page.locator('main.chat-view')).toBeVisible();
		await expect(page.locator('.empty-state')).not.toBeVisible();
	});

	test('delete conversation decreases sidebar count', async ({ page }) => {
		const initialCount = await page.locator('.conversation-item').count();

		// Create a fresh conversation to delete, wait for it to appear
		await page.getByRole('button', { name: 'New', exact: true }).click();
		await expect(page.locator('.conversation-item')).toHaveCount(initialCount + 1);

		// Hover the first item and delete it
		await page.locator('.conversation-item').first().hover();
		await page.locator('.conversation-item').first().locator('.delete-btn').click();

		await expect(page.locator('.conversation-item')).toHaveCount(initialCount);
	});

	test('multiple conversations can be created and switched', async ({ page }) => {
		const initialCount = await page.locator('.conversation-item').count();

		await page.getByRole('button', { name: 'New', exact: true }).click();
		await page.getByRole('button', { name: 'New', exact: true }).click();

		await expect(page.locator('.conversation-item')).toHaveCount(initialCount + 2);

		// Click the first conversation — it should be active
		await page.locator('.conversation-item').first().click();
		await expect(page.locator('.conversation-item').first()).toHaveClass(/active/);

		// Click the second — first should no longer be active
		await page.locator('.conversation-item').nth(1).click();
		await expect(page.locator('.conversation-item').nth(1)).toHaveClass(/active/);
		await expect(page.locator('.conversation-item').first()).not.toHaveClass(/active/);
	});

	test('logout clears state and shows login form', async ({ page }) => {
		await page.getByRole('button', { name: 'Sign out' }).click();

		await expect(page.locator('aside.sidebar')).not.toBeVisible();
		await expect(page.getByRole('heading', { name: 'Claude Chat' })).toBeVisible();
		await expect(page.getByPlaceholder('you@example.com')).toBeVisible();
	});
});
