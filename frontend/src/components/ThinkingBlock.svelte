<script lang="ts">
	import type { ThinkingEntry } from '$lib/types';

	let { entries }: { entries: ThinkingEntry[] } = $props();
</script>

{#if entries.length > 0}
	<details class="thinking" open>
		<summary>Thinking</summary>
		<div class="thinking-content">
			{#each entries as entry}
				<pre>{entry.thinking}</pre>
			{/each}
		</div>
	</details>
{/if}

<style>
	.thinking {
		border-radius: var(--radius);
		background: var(--thinking-bg);
		border: 1px solid #2e2640;
		overflow: hidden;
		margin-bottom: 8px;
	}

	summary {
		padding: 8px 12px;
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--text-muted);
		cursor: pointer;
		user-select: none;
	}

	summary:hover {
		color: var(--text);
	}

	.thinking-content {
		padding: 0 12px 12px;
	}

	pre {
		white-space: pre-wrap;
		word-break: break-word;
		font-size: 0.8125rem;
		color: var(--text-muted);
		line-height: 1.6;
	}
</style>
