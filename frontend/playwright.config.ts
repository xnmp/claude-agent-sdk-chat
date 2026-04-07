import { defineConfig } from '@playwright/test';

export default defineConfig({
	testDir: 'e2e',
	fullyParallel: true,
	forbidOnly: !!process.env.CI,
	retries: 0,
	use: {
		baseURL: 'http://localhost:5173'
	},
	webServer: {
		command: 'bun run dev',
		port: 5173,
		reuseExistingServer: true
	}
});
