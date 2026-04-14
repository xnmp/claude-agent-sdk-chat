<script lang="ts">
	/**
	 * Dumb markdown renderer that honors a typewriter cursor.
	 *
	 * The typewriter lives in +page.svelte (one ticker for the whole app). This
	 * component is a passive view: it takes the full `text` and the current
	 * `revealed` count and renders `text.slice(0, revealed)` as markdown.
	 *
	 * Because `revealed` is a reactive $state property on the block object, any
	 * mutation by the ticker triggers a re-render here automatically.
	 */

	import { renderMarkdown } from '$lib/markdown';

	let { text, revealed }: { text: string; revealed: number } = $props();

	let visibleText = $derived(text.slice(0, Math.max(0, Math.min(text.length, revealed))));
	let html = $derived(renderMarkdown(visibleText));
</script>

{@html html}
