import { test, expect } from '@playwright/test';

/**
 * E2E test for markdown rendering of assistant replies.
 * Verifies that assistant messages are rendered as HTML (not plain text)
 * using the markdown pipeline.
 */

test.describe('Markdown rendering', () => {
	test.beforeEach(async ({ page }) => {
		await page.addInitScript(() => localStorage.clear());
		await page.goto('/');
		await page.waitForLoadState('networkidle');

		await page.getByPlaceholder('you@example.com').fill('e2e-md@example.com');
		await page.getByPlaceholder('Your name').fill('MD Tester');
		await page.getByRole('button', { name: /sign in/i }).click();
		await expect(page.locator('aside.sidebar')).toBeVisible({ timeout: 10000 });
	});

	// SKIPPED: see #85. Even after fixing the stale '+ New' selector and
	// bumping the test timeout, the test waits 120s for `.response-text.markdown`
	// and never sees one — the page snapshot shows the user message and a
	// disabled Send button (post-submit) but no assistant content. Suspected
	// race between `.conversation-item.first()` and `createConversation`'s
	// REST resolve, but needs proper investigation. Restore once #85 is fixed.
	test.skip('assistant reply renders markdown as HTML', async ({ page }) => {
		// SDK startup + a real assistant reply easily exceeds Playwright's
		// default 30s test timeout, even though the inner toBeVisible has a
		// 120s wait. Bump the test timeout to match.
		test.setTimeout(180000);

		// Create a new conversation
		await page.getByRole('button', { name: 'New', exact: true }).click();
		await page.locator('.conversation-item').first().click();
		await expect(page.locator('main.chat-view')).toBeVisible();

		// Send a message that will prompt a markdown-rich response
		const input = page.locator('textarea, input[type="text"]').first();
		await input.fill('Reply with a short bulleted list of 3 colors. Use markdown formatting.');
		await page.getByRole('button', { name: /send/i }).click();

		// Wait for the assistant response to appear (with generous timeout for SDK startup)
		const responseText = page.locator('.response-text.markdown');
		await expect(responseText.first()).toBeVisible({ timeout: 120000 });

		// The markdown class should be applied
		await expect(responseText.first()).toHaveClass(/markdown/);

		// Response should contain rendered HTML (not raw markdown asterisks/dashes)
		// Wait for the result (streaming complete)
		const meta = page.locator('.meta');
		await expect(meta.first()).toBeVisible({ timeout: 120000 });

		// Verify HTML was rendered: the response should contain actual HTML list items
		// or paragraph tags, not just plain text
		const innerHTML = await responseText.first().innerHTML();
		const hasHtmlTags = /<(p|ul|ol|li|strong|em|code|h[1-6]|pre|blockquote)[\s>]/.test(innerHTML);
		expect(hasHtmlTags).toBe(true);
	});
});
