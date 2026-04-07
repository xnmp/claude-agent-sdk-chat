<script lang="ts">
	import type { ThinkingEntry } from '$lib/types';

	let { entries }: { entries: ThinkingEntry[] } = $props();
</script>

{#if entries.length > 0}
	<details class="thinking" open>
		<summary>
			<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
				<circle cx="7" cy="7" r="5.5" />
				<path d="M5.5 5.5C5.5 4.67 6.17 4 7 4C7.83 4 8.5 4.67 8.5 5.5C8.5 6.33 7.83 7 7 7V8" />
				<circle cx="7" cy="9.5" r="0.5" fill="currentColor" />
			</svg>
			Thinking
		</summary>
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
		border: 1px solid var(--thinking-border);
		overflow: hidden;
		margin-bottom: 6px;
	}

	summary {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 8px 12px;
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--text-muted);
		cursor: pointer;
		user-select: none;
		transition: color 0.12s ease;
	}

	summary:hover {
		color: var(--text-secondary);
	}

	summary::-webkit-details-marker {
		display: none;
	}

	summary::marker {
		content: '';
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
