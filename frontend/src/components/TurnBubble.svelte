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

	// For live turns, derive sub-message visibility
	let liveHasSubMessages = $derived(
		liveTurn ? liveTurn.thinking.length > 0 || liveTurn.tool_calls.length > 0 : false
	);

	// For persisted assistant messages
	let hasSubMessages = $derived(
		assistantContent
			? assistantContent.thinking.length > 0 || assistantContent.tool_calls.length > 0
			: false
	);

	let showSubMessages = $state(false);
</script>

{#if isUser && userContent}
	<div class="turn user">
		<div class="bubble user-bubble">
			<p>{userContent.text}</p>
		</div>
	</div>
{:else if isLive && liveTurn}
	<div class="turn assistant">
		<div class="bubble assistant-bubble">
			{#if liveHasSubMessages}
				<button class="toggle-sub" onclick={() => (showSubMessages = !showSubMessages)}>
					{showSubMessages ? 'Hide' : 'Show'}
					{liveTurn.tool_calls.length} tool call{liveTurn.tool_calls.length !== 1 ? 's' : ''}
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
	<div class="turn assistant">
		<div class="bubble assistant-bubble">
			{#if hasSubMessages}
				<button class="toggle-sub" onclick={() => (showSubMessages = !showSubMessages)}>
					{showSubMessages ? 'Hide' : 'Show'}
					{assistantContent.tool_calls.length} tool call{assistantContent.tool_calls.length !== 1
						? 's'
						: ''}
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
						<span>{(assistantContent.duration_ms / 1000).toFixed(1)}s</span>
					{/if}
				</div>
			{/if}
		</div>
	</div>
{/if}

<style>
	.turn {
		padding: 4px 0;
	}

	.bubble {
		max-width: 85%;
		padding: 12px 16px;
		border-radius: var(--radius);
		line-height: 1.6;
		font-size: 0.9375rem;
	}

	.user-bubble {
		background: var(--accent);
		color: white;
		margin-left: auto;
		border-bottom-right-radius: 2px;
	}

	.assistant-bubble {
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-bottom-left-radius: 2px;
	}

	.user-bubble p {
		white-space: pre-wrap;
		word-break: break-word;
	}

	.response-text {
		white-space: pre-wrap;
		word-break: break-word;
	}

	.toggle-sub {
		font-size: 0.8125rem;
		color: var(--accent);
		padding: 4px 0;
		margin-bottom: 4px;
	}

	.toggle-sub:hover {
		text-decoration: underline;
	}

	.sub-messages {
		display: flex;
		flex-direction: column;
		gap: 6px;
		margin-bottom: 10px;
		padding-bottom: 10px;
		border-bottom: 1px solid var(--border);
	}

	.meta {
		display: flex;
		gap: 12px;
		margin-top: 8px;
		font-size: 0.75rem;
		color: var(--text-dim);
	}

	.streaming-indicator {
		display: flex;
		gap: 4px;
		padding: 4px 0;
	}

	.dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--text-dim);
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
			opacity: 0.3;
		}
		40% {
			opacity: 1;
		}
	}
</style>
