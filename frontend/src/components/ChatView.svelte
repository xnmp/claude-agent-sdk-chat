<script lang="ts">
	import { tick } from 'svelte';
	import type { Message, LiveTurn } from '$lib/types';
	import type { WsStatus } from '$lib/ws';
	import TurnBubble from './TurnBubble.svelte';
	import MessageInput from './MessageInput.svelte';

	let {
		messages,
		liveTurn,
		isStreaming,
		wsStatus,
		onSend,
		onInterrupt
	}: {
		messages: Message[];
		liveTurn: LiveTurn | null;
		isStreaming: boolean;
		wsStatus: WsStatus;
		onSend: (content: string) => void;
		onInterrupt: () => void;
	} = $props();

	let scrollContainer: HTMLDivElement | undefined = $state();

	// Auto-scroll is a genuine DOM side effect — $effect is appropriate here
	$effect(() => {
		// Track reactive dependencies
		void messages.length;
		void liveTurn?.text;
		void liveTurn?.tool_calls.length;

		tick().then(() => {
			if (scrollContainer) {
				scrollContainer.scrollTop = scrollContainer.scrollHeight;
			}
		});
	});

	let noConversation = $derived(wsStatus === 'disconnected' && messages.length === 0);
</script>

<main class="chat-view">
	{#if noConversation}
		<div class="empty-state">
			<h2>Claude Agent Chat</h2>
			<p>Create or select a conversation to get started.</p>
		</div>
	{:else}
		<div class="messages" bind:this={scrollContainer}>
			{#each messages as msg (msg.id)}
				<TurnBubble message={msg} />
			{/each}

			{#if liveTurn}
				<TurnBubble {liveTurn} isLive={true} />
			{/if}
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
	}

	.messages {
		flex: 1;
		overflow-y: auto;
		padding: 24px;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.empty-state {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 8px;
		color: var(--text-dim);
	}

	.empty-state h2 {
		font-size: 1.25rem;
		color: var(--text-muted);
	}

	.empty-state p {
		font-size: 0.9375rem;
	}
</style>
