<script lang="ts">
	import { onMount } from 'svelte';
	import type { Message, UserContent, AssistantContent, LiveTurn } from '$lib/types';
	import type { Settings } from '$lib/settings';
	import { renderMarkdown } from '$lib/markdown';
	import ThinkingBlock from './ThinkingBlock.svelte';
	import ToolCall from './ToolCall.svelte';

	let {
		message = null,
		liveTurn = null,
		isLive = false,
		settings = { theme: 'light', showCost: true, showDuration: true }
	}: {
		message?: Message | null;
		liveTurn?: LiveTurn | null;
		isLive?: boolean;
		settings?: Settings;
	} = $props();

	// Elapsed timer for live turns — only depends on isLive, not liveTurn content
	let elapsedMs = $state(0);

	$effect(() => {
		if (!isLive) return;
		const start = Date.now();
		elapsedMs = 0;
		const timer = setInterval(() => {
			elapsedMs = Date.now() - start;
		}, 100);
		return () => clearInterval(timer);
	});

	let isUser = $derived(message?.role === 'user');
	let userContent = $derived(isUser ? (message?.content as UserContent) : null);
	let assistantContent = $derived(!isUser && message ? (message.content as AssistantContent) : null);

	let liveHasThinking = $derived(liveTurn ? liveTurn.thinking.length > 0 : false);
	let liveToolCount = $derived(liveTurn ? liveTurn.tool_calls.length : 0);
	let liveHasSubMessages = $derived(liveHasThinking || liveToolCount > 0);

	let hasThinking = $derived(assistantContent ? assistantContent.thinking.length > 0 : false);
	let toolCallCount = $derived(assistantContent ? assistantContent.tool_calls.length : 0);
	let hasSubMessages = $derived(hasThinking || toolCallCount > 0);

	let showSubMessages = $state(false);
</script>

{#if isUser && userContent}
	<div class="turn user-turn">
		<div class="bubble user-bubble">
			<p>{userContent.text}</p>
		</div>
	</div>
{:else if isLive && liveTurn}
	<div class="turn assistant-turn">
		<div class="bubble assistant-bubble">
			{#if liveHasSubMessages}
				<button class="toggle-sub" onclick={() => (showSubMessages = !showSubMessages)}>
					<svg class="toggle-icon" class:open={showSubMessages} width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
						<polyline points="4,2 8,6 4,10" />
					</svg>
					{#if liveHasThinking && liveToolCount === 0}
						Thinking...
					{:else if liveHasThinking && liveToolCount > 0}
						Thought &middot; {liveToolCount} tool call{liveToolCount !== 1 ? 's' : ''}
					{:else}
						{liveToolCount} tool call{liveToolCount !== 1 ? 's' : ''}
					{/if}
				</button>

				{#if showSubMessages}
					<div class="sub-messages">
						{#if liveHasThinking}
							<ThinkingBlock entries={liveTurn.thinking} />
						{/if}
						{#each liveTurn.tool_calls as tool (tool.id)}
							<ToolCall {tool} />
						{/each}
					</div>
				{/if}
			{/if}

			{#if liveTurn.text}
				<div class="response-text markdown">{@html renderMarkdown(liveTurn.text)}</div>
			{:else}
				<div class="streaming-indicator">
					<span class="dot"></span>
					<span class="dot"></span>
					<span class="dot"></span>
				</div>
			{/if}

			{#if settings.showDuration && elapsedMs > 0}
				<div class="meta">
					<span>{(elapsedMs / 1000).toFixed(1)}s</span>
				</div>
			{/if}
		</div>
	</div>
{:else if assistantContent}
	<div class="turn assistant-turn">
		<div class="bubble assistant-bubble">
			{#if hasSubMessages}
				<button class="toggle-sub" onclick={() => (showSubMessages = !showSubMessages)}>
					<svg class="toggle-icon" class:open={showSubMessages} width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
						<polyline points="4,2 8,6 4,10" />
					</svg>
					{#if hasThinking && toolCallCount === 0}
						Thought
					{:else if hasThinking && toolCallCount > 0}
						Thought &middot; {toolCallCount} tool call{toolCallCount !== 1 ? 's' : ''}
					{:else}
						{toolCallCount} tool call{toolCallCount !== 1 ? 's' : ''}
					{/if}
				</button>

				{#if showSubMessages}
					<div class="sub-messages">
						{#if hasThinking}
							<ThinkingBlock entries={assistantContent.thinking} />
						{/if}
						{#each assistantContent.tool_calls as tool (tool.id)}
							<ToolCall {tool} />
						{/each}
					</div>
				{/if}
			{/if}

			{#if assistantContent.text}
				<div class="response-text markdown">{@html renderMarkdown(assistantContent.text)}</div>
			{/if}

			{#if (settings.showCost && assistantContent.total_cost_usd > 0) || (settings.showDuration && assistantContent.duration_ms > 0)}
				<div class="meta">
					{#if settings.showCost && assistantContent.total_cost_usd > 0}
						<span>${assistantContent.total_cost_usd.toFixed(4)}</span>
					{/if}
					{#if settings.showCost && settings.showDuration && assistantContent.total_cost_usd > 0 && assistantContent.duration_ms > 0}
						<span class="meta-sep">&middot;</span>
					{/if}
					{#if settings.showDuration && assistantContent.duration_ms > 0}
						<span>{(assistantContent.duration_ms / 1000).toFixed(1)}s</span>
					{/if}
				</div>
			{/if}

			{#if assistantContent.created_files && assistantContent.created_files.length > 0}
				<div class="created-files">
					<span class="files-label">Files:</span>
					{#each assistantContent.created_files as file}
						<a
							class="file-link"
							href="http://localhost:8000/api/output/{file}"
							download={file.split('/').pop()}
							target="_blank"
						>
							<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
								<path d="M6 2v6M3 6l3 3 3-3M2 10h8" />
							</svg>
							{file}
						</a>
					{/each}
				</div>
			{/if}
		</div>
	</div>
{/if}

<style>
	.turn {
		padding: 6px 0;
	}

	.bubble {
		max-width: 88%;
		padding: 14px 18px;
		border-radius: var(--radius-lg);
		line-height: 1.6;
		font-size: 0.9375rem;
	}

	/* User messages */
	.user-bubble {
		background: var(--text);
		color: var(--bg-surface);
		margin-left: auto;
		border-bottom-right-radius: 4px;
		box-shadow: var(--shadow-sm);
	}

	.user-bubble p {
		white-space: pre-wrap;
		word-break: break-word;
	}

	/* Assistant messages */
	.assistant-bubble {
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-bottom-left-radius: 4px;
		box-shadow: var(--shadow-sm);
	}

	.response-text {
		word-break: break-word;
	}

	/* Markdown typography */
	.response-text.markdown :global(p) {
		margin: 0 0 0.6em;
	}

	.response-text.markdown :global(p:last-child) {
		margin-bottom: 0;
	}

	.response-text.markdown :global(h1),
	.response-text.markdown :global(h2),
	.response-text.markdown :global(h3),
	.response-text.markdown :global(h4) {
		margin: 0.8em 0 0.4em;
		font-weight: 600;
		line-height: 1.3;
	}

	.response-text.markdown :global(h1) { font-size: 1.3em; }
	.response-text.markdown :global(h2) { font-size: 1.15em; }
	.response-text.markdown :global(h3) { font-size: 1.05em; }

	.response-text.markdown :global(ul),
	.response-text.markdown :global(ol) {
		margin: 0.4em 0;
		padding-left: 1.5em;
	}

	.response-text.markdown :global(li) {
		margin: 0.2em 0;
	}

	.response-text.markdown :global(code) {
		font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
		font-size: 0.875em;
		background: var(--bg-inset, rgba(0, 0, 0, 0.06));
		padding: 0.15em 0.35em;
		border-radius: 4px;
	}

	.response-text.markdown :global(pre) {
		margin: 0.6em 0;
		padding: 0.8em 1em;
		background: var(--bg-inset, rgba(0, 0, 0, 0.06));
		border-radius: var(--radius-sm, 6px);
		overflow-x: auto;
	}

	.response-text.markdown :global(pre code) {
		background: none;
		padding: 0;
		font-size: 0.85em;
	}

	.response-text.markdown :global(blockquote) {
		margin: 0.5em 0;
		padding: 0.3em 0.8em;
		border-left: 3px solid var(--accent, #6366f1);
		color: var(--text-dim, #666);
	}

	.response-text.markdown :global(a) {
		color: var(--accent, #6366f1);
		text-decoration: underline;
	}

	.response-text.markdown :global(table) {
		border-collapse: collapse;
		margin: 0.5em 0;
		width: 100%;
	}

	.response-text.markdown :global(th),
	.response-text.markdown :global(td) {
		border: 1px solid var(--border, #e2e8f0);
		padding: 0.4em 0.7em;
		text-align: left;
	}

	.response-text.markdown :global(th) {
		font-weight: 600;
		background: var(--bg-inset, rgba(0, 0, 0, 0.03));
	}

	.response-text.markdown :global(hr) {
		border: none;
		border-top: 1px solid var(--border, #e2e8f0);
		margin: 0.8em 0;
	}

	/* Tool call toggle */
	.toggle-sub {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--accent);
		padding: 4px 8px;
		margin: -2px -8px 6px;
		border-radius: var(--radius-sm);
		transition: background 0.12s ease;
	}

	.toggle-sub:hover {
		background: var(--accent-subtle);
	}

	.toggle-icon {
		transition: transform 0.15s ease;
	}

	.toggle-icon.open {
		transform: rotate(90deg);
	}

	.sub-messages {
		display: flex;
		flex-direction: column;
		gap: 6px;
		margin-bottom: 12px;
		padding-bottom: 12px;
		border-bottom: 1px solid var(--border);
	}

	/* Meta info */
	.meta {
		display: flex;
		align-items: center;
		gap: 6px;
		margin-top: 10px;
		padding-top: 10px;
		border-top: 1px solid var(--border);
		font-size: 0.75rem;
		color: var(--text-dim);
		font-variant-numeric: tabular-nums;
	}

	.meta-sep {
		color: var(--border-strong);
	}

	/* Download links */
	.created-files {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 6px;
		margin-top: 8px;
		padding-top: 8px;
		border-top: 1px solid var(--border);
		font-size: 0.75rem;
	}

	.files-label {
		color: var(--text-dim);
		font-weight: 500;
	}

	.file-link {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		padding: 3px 8px;
		background: var(--accent-subtle);
		color: var(--accent);
		border-radius: var(--radius-sm);
		font-family: var(--font-mono);
		font-size: 0.6875rem;
		text-decoration: none;
		transition: background 0.12s ease;
	}

	.file-link:hover {
		background: var(--accent-muted);
		text-decoration: none;
	}

	/* Streaming indicator */
	.streaming-indicator {
		display: flex;
		gap: 5px;
		padding: 4px 0;
	}

	.dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: var(--accent);
		opacity: 0.35;
		animation: pulse 1.4s ease-in-out infinite;
	}

	.dot:nth-child(2) {
		animation-delay: 0.2s;
	}

	.dot:nth-child(3) {
		animation-delay: 0.4s;
	}

	@keyframes pulse {
		0%,
		80%,
		100% {
			opacity: 0.2;
			transform: scale(0.85);
		}
		40% {
			opacity: 1;
			transform: scale(1);
		}
	}
</style>
