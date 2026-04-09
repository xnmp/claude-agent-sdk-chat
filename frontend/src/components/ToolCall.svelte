<script lang="ts">
	import type { ToolCallEntry } from '$lib/types';

	let { tool }: { tool: ToolCallEntry } = $props();

	let statusLabel = $derived(
		tool.result === null ? 'running...' : tool.is_error ? 'error' : 'done'
	);

	let statusClass = $derived(
		tool.result === null ? 'running' : tool.is_error ? 'error' : 'success'
	);

	let description = $derived(
		typeof tool.input.description === 'string' ? tool.input.description : null
	);
</script>

<details class="tool-call">
	<summary>
		<svg class="tool-icon" width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
			<path d="M7.5 1.5L5.5 5.5H1.5L5.5 11.5L7.5 7.5H11.5L7.5 1.5Z" />
		</svg>
		<span class="tool-name">{tool.name}</span>
		{#if description}
			<span class="tool-description">{description}</span>
		{/if}
		<span class="status {statusClass}">{statusLabel}</span>
	</summary>
	<div class="tool-detail">
		{#if Object.keys(tool.input).length > 0}
			<div class="section">
				<span class="label">Input</span>
				<pre>{JSON.stringify(tool.input, null, 2)}</pre>
			</div>
		{/if}
		{#if tool.result !== null}
			<div class="section">
				<span class="label">Output</span>
				<pre class:error-text={tool.is_error}>{tool.result}</pre>
			</div>
		{/if}
	</div>
</details>

<style>
	.tool-call {
		border-radius: var(--radius);
		background: var(--tool-bg);
		border: 1px solid var(--tool-border);
		overflow: hidden;
	}

	summary {
		display: flex;
		align-items: center;
		gap: 7px;
		padding: 7px 12px;
		font-size: 0.8125rem;
		cursor: pointer;
		user-select: none;
		transition: background 0.12s ease;
	}

	summary:hover {
		background: rgba(0, 0, 0, 0.02);
	}

	summary::-webkit-details-marker {
		display: none;
	}

	summary::marker {
		content: '';
	}

	.tool-icon {
		color: var(--text-muted);
		flex-shrink: 0;
	}

	.tool-name {
		font-family: var(--font-mono);
		font-weight: 500;
		font-size: 0.8125rem;
		color: var(--text-secondary);
		flex-shrink: 0;
	}

	.tool-description {
		font-size: 0.8125rem;
		color: var(--text-muted);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		min-width: 0;
	}

	.status {
		font-size: 0.6875rem;
		font-weight: 600;
		padding: 2px 8px;
		border-radius: 10px;
		margin-left: auto;
		letter-spacing: 0.02em;
		text-transform: uppercase;
	}

	.status.running {
		color: var(--accent);
		background: var(--accent-subtle);
	}

	.status.success {
		color: var(--success);
		background: var(--success-bg);
	}

	.status.error {
		color: var(--error);
		background: var(--error-bg);
	}

	.tool-detail {
		padding: 0 12px 12px;
	}

	.section {
		margin-top: 8px;
	}

	.label {
		display: block;
		font-size: 0.6875rem;
		color: var(--text-dim);
		margin-bottom: 4px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		font-weight: 600;
	}

	pre {
		white-space: pre-wrap;
		word-break: break-word;
		font-size: 0.8125rem;
		color: var(--text-muted);
		line-height: 1.55;
		max-height: 300px;
		overflow-y: auto;
		background: rgba(0, 0, 0, 0.02);
		padding: 8px 10px;
		border-radius: var(--radius-sm);
	}

	.error-text {
		color: var(--error);
	}
</style>
