<script lang="ts">
	import type { Message, UserContent, AssistantContent, LiveTurn } from '$lib/types';
	import ThinkingBlock from './ThinkingBlock.svelte';
	import ToolCall from './ToolCall.svelte';

	let {
		message = null,
		liveTurn = null,
		isLive = false
	}: {
		message?: Message | null;
		liveTurn?: LiveTurn | null;
		isLive?: boolean;
	} = $props();

	let isUser = $derived(message?.role === 'user');
	let userContent = $derived(isUser ? (message?.content as UserContent) : null);
	let assistantContent = $derived(!isUser && message ? (message.content as AssistantContent) : null);

	let liveHasSubMessages = $derived(
		liveTurn ? liveTurn.thinking.length > 0 || liveTurn.tool_calls.length > 0 : false
	);

	let hasSubMessages = $derived(
		assistantContent
			? assistantContent.thinking.length > 0 || assistantContent.tool_calls.length > 0
			: false
	);

	let showSubMessages = $state(false);

	let toolCallCount = $derived(
		isLive && liveTurn
			? liveTurn.tool_calls.length
			: assistantContent
				? assistantContent.tool_calls.length
				: 0
	);
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
					{toolCallCount} tool call{toolCallCount !== 1 ? 's' : ''}
				</button>

				{#if showSubMessages}
					<div class="sub-messages">
						<ThinkingBlock entries={liveTurn.thinking} />
						{#each liveTurn.tool_calls as tool (tool.id)}
							<ToolCall {tool} />
						{/each}
					</div>
				{/if}
			{/if}

			{#if liveTurn.text}
				<div class="response-text">{liveTurn.text}</div>
			{:else}
				<div class="streaming-indicator">
					<span class="dot"></span>
					<span class="dot"></span>
					<span class="dot"></span>
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
					{toolCallCount} tool call{toolCallCount !== 1 ? 's' : ''}
				</button>

				{#if showSubMessages}
					<div class="sub-messages">
						<ThinkingBlock entries={assistantContent.thinking} />
						{#each assistantContent.tool_calls as tool (tool.id)}
							<ToolCall {tool} />
						{/each}
					</div>
				{/if}
			{/if}

			{#if assistantContent.text}
				<div class="response-text">{assistantContent.text}</div>
			{/if}

			{#if assistantContent.total_cost_usd > 0}
				<div class="meta">
					<span>${assistantContent.total_cost_usd.toFixed(4)}</span>
					{#if assistantContent.duration_ms > 0}
						<span class="meta-sep">&middot;</span>
						<span>{(assistantContent.duration_ms / 1000).toFixed(1)}s</span>
					{/if}
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
		white-space: pre-wrap;
		word-break: break-word;
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
