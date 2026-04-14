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
		<svg class="expand-chevron" width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
			<polyline points="3,1.5 7,5 3,8.5" />
		</svg>
		<svg class="tool-icon" width="12" height="12" viewBox="0 0 13 13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
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
		gap: 6px;
		padding: 7px 11px;
		font-size: 0.8125rem;
		cursor: pointer;
		user-select: none;
		transition: background var(--transition-fast);
	}

	summary:hover {
		background: rgba(45, 138, 78, 0.04);
	}

	:global([data-theme='dark']) summary:hover {
		background: rgba(76, 175, 106, 0.06);
	}

	summary::-webkit-details-marker {
		display: none;
	}

	summary::marker {
		content: '';
	}

	/* Rotate chevron when open */
	.expand-chevron {
		color: var(--text-dim);
		flex-shrink: 0;
		transition: transform var(--transition-fast), color var(--transition-fast);
	}

	details[open] .expand-chevron {
		transform: rotate(90deg);
		color: var(--text-muted);
	}

	.tool-icon {
		color: var(--success);
		flex-shrink: 0;
		opacity: 0.7;
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
		font-size: 0.625rem;
		font-weight: 700;
		padding: 2px 7px;
		border-radius: 8px;
		margin-left: auto;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		flex-shrink: 0;
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
		padding: 0 11px 11px;
		border-top: 1px solid var(--tool-border);
	}

	.section {
		margin-top: 9px;
	}

	.label {
		display: block;
		font-size: 0.625rem;
		color: var(--text-dim);
		margin-bottom: 5px;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		font-weight: 700;
	}

	pre {
		white-space: pre-wrap;
		word-break: break-word;
		font-size: 0.8125rem;
		color: var(--text-secondary);
		line-height: 1.55;
		max-height: 300px;
		overflow-y: auto;
		background: var(--bg-inset);
		border: 1px solid var(--border);
		padding: 8px 10px;
		border-radius: var(--radius-sm);
	}

	.error-text {
		color: var(--error);
	}
</style>
