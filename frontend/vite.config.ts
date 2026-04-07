import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	test: {
		include: ['tests/**/*.test.ts'],
		environment: 'jsdom',
		setupFiles: ['tests/setup.ts'],
		alias: {
			'$lib': new URL('./src/lib', import.meta.url).pathname
		}
	},
	resolve: {
		conditions: ['browser']
	}
});
