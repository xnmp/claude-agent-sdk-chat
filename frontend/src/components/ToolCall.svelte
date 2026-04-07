<script lang="ts">
	import type { ToolCallEntry } from '$lib/types';

	let { tool }: { tool: ToolCallEntry } = $props();

	let statusLabel = $derived(
		tool.result === null ? 'running...' : tool.is_error ? 'error' : 'done'
	);

	let statusClass = $derived(
		tool.result === null ? 'running' : tool.is_error ? 'error' : 'success'
	);
</script>

<details class="tool-call">
	<summary>
		<span class="tool-name">{tool.name}</span>
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
		border-radius: 6px;
		background: var(--tool-bg);
		border: 1px solid #242e24;
		overflow: hidden;
	}

	summary {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 6px 10px;
		font-size: 0.8125rem;
		cursor: pointer;
		user-select: none;
	}

	summary:hover {
		background: rgba(255, 255, 255, 0.03);
	}

	.tool-name {
		font-family: var(--font-mono);
		font-weight: 500;
	}

	.status {
		font-size: 0.75rem;
		padding: 1px 6px;
		border-radius: 4px;
		margin-left: auto;
	}

	.status.running {
		color: var(--accent);
		background: rgba(124, 107, 240, 0.15);
	}

	.status.success {
		color: var(--success);
		background: rgba(85, 170, 85, 0.15);
	}

	.status.error {
		color: var(--error);
		background: rgba(238, 85, 85, 0.15);
	}

	.tool-detail {
		padding: 0 10px 10px;
	}

	.section {
		margin-top: 6px;
	}

	.label {
		display: block;
		font-size: 0.75rem;
		color: var(--text-dim);
		margin-bottom: 2px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	pre {
		white-space: pre-wrap;
		word-break: break-word;
		font-size: 0.8125rem;
		color: var(--text-muted);
		line-height: 1.5;
		max-height: 300px;
		overflow-y: auto;
	}

	.error-text {
		color: var(--error);
	}
</style>
