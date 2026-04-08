<script lang="ts">
	import { tick } from 'svelte';
	import type { Message, LiveTurn } from '$lib/types';
	import type { WsStatus } from '$lib/ws';
	import type { Settings } from '$lib/settings';
	import TurnBubble from './TurnBubble.svelte';
	import MessageInput from './MessageInput.svelte';

	let {
		messages,
		liveTurn,
		isStreaming,
		wsStatus,
		settings,
		suggestions = [],
		onSend,
		onInterrupt,
		onSuggestionClick
	}: {
		messages: Message[];
		liveTurn: LiveTurn | null;
		isStreaming: boolean;
		wsStatus: WsStatus;
		settings: Settings;
		suggestions?: string[];
		onSend: (content: string, files: File[]) => void;
		onInterrupt: () => void;
		onSuggestionClick?: (question: string) => void;
	} = $props();

	let scrollContainer: HTMLDivElement | undefined = $state();

	// Auto-scroll is a genuine DOM side effect — $effect is appropriate here
	$effect(() => {
		void messages.length;
		void liveTurn?.text;
		void liveTurn?.tool_calls.length;

		tick().then(() => {
			if (scrollContainer) {
				scrollContainer.scrollTo({
					top: scrollContainer.scrollHeight,
					behavior: 'smooth'
				});
			}
		});
	});

	let noConversation = $derived(wsStatus === 'disconnected' && messages.length === 0);
</script>

<main class="chat-view">
	{#if noConversation}
		<div class="empty-state">
			<div class="empty-icon">
				<svg width="48" height="48" viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
					<path d="M8 12C8 9.79 9.79 8 12 8H36C38.21 8 40 9.79 40 12V30C40 32.21 38.21 34 36 34H26L18 40V34H12C9.79 34 8 32.21 8 30V12Z" />
					<circle cx="18" cy="21" r="1.5" fill="currentColor" stroke="none" />
					<circle cx="24" cy="21" r="1.5" fill="currentColor" stroke="none" />
					<circle cx="30" cy="21" r="1.5" fill="currentColor" stroke="none" />
				</svg>
			</div>
			<h2>Start a conversation</h2>
			<p>Create or select a conversation from the sidebar.</p>
		</div>
	{:else}
		<div class="messages" bind:this={scrollContainer}>
			<div class="messages-inner">
				{#each messages as msg (msg.id)}
					<TurnBubble message={msg} {settings} />
				{/each}

				{#if liveTurn}
					<TurnBubble {liveTurn} isLive={true} {settings} />
				{/if}

				{#if suggestions.length > 0 && !isStreaming}
					<div class="suggestions">
						{#each suggestions as question}
							<button class="suggestion-chip" onclick={() => onSuggestionClick?.(question)}>
								{question}
							</button>
						{/each}
					</div>
				{/if}
			</div>
		</div>

		<MessageInput
			{isStreaming}
			disabled={wsStatus !== 'connected'}
			{onSend}
			{onInterrupt}
		/>
	{/if}
</main>

<style>
	.chat-view {
		flex: 1;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		min-width: 0;
		background: var(--bg);
	}

	.messages {
		flex: 1;
		overflow-y: auto;
		padding: 24px 0;
	}

	.messages-inner {
		max-width: 768px;
		margin: 0 auto;
		padding: 0 24px;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.empty-state {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 12px;
	}

	.empty-icon {
		color: var(--text-dim);
		margin-bottom: 4px;
	}

	.empty-state h2 {
		font-family: var(--font-display);
		font-size: 1.5rem;
		font-weight: 400;
		font-style: italic;
		color: var(--text);
		letter-spacing: -0.02em;
	}

	.empty-state p {
		font-size: 0.9375rem;
		color: var(--text-muted);
	}

	.suggestions {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		padding: 12px 0;
	}

	.suggestion-chip {
		padding: 8px 14px;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		font-size: 0.8125rem;
		color: var(--text-secondary);
		transition: all 0.15s ease;
		text-align: left;
		line-height: 1.4;
	}

	.suggestion-chip:hover {
		border-color: var(--accent);
		color: var(--accent);
		background: var(--accent-subtle);
	}
</style>
