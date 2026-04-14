import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	compilerOptions: {
		// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
	},
	kit: {
		// Static build: the FastAPI backend serves the resulting assets from
		// frontend/build at `/`. `fallback` gives every unmatched client-side
		// route index.html so client routing works behind the static mount.
		adapter: adapter({
			fallback: 'index.html'
		})
	}
};

export default config;
