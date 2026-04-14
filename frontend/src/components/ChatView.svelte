<script lang="ts">
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
		conversationId = null,
		onSend,
		onInterrupt
	}: {
		messages: Message[];
		liveTurn: LiveTurn | null;
		isStreaming: boolean;
		wsStatus: WsStatus;
		settings: Settings;
		suggestions?: string[];
		conversationId?: string | null;
		onSend: (content: string, files: File[]) => void;
		onInterrupt: () => void;
	} = $props();

	let scrollContainer: HTMLDivElement | undefined = $state();
	let messagesInner: HTMLDivElement | undefined = $state();
	let messageInput: MessageInput | undefined = $state();

	// Auto-follow stickiness: while sticky, ResizeObserver scrolls to the
	// bottom on every height change. Wheel-up disengages immediately so the
	// user can read a long essay while the rest of it streams; scrolling
	// back to within REENGAGE_PX of the bottom re-engages.
	//
	// We deliberately separate user intent (wheel) from position checking
	// (scroll). Position-only detection is racy: the programmatic scroll in
	// the ResizeObserver fires a scroll event AFTER content may have grown
	// further, making `distance > 0` look like a user scroll-away. Watching
	// wheel events captures intent directly and avoids the race.
	let stickToBottom = $state(true);
	const REENGAGE_PX = 10;

	export function focusInput() {
		messageInput?.focus();
	}

	function handleScroll() {
		// Only used to RE-engage when the user scrolls back to the bottom.
		// Disengage is wheel-driven so we can't be tricked by a programmatic
		// scroll firing this handler with a stale distance.
		if (!scrollContainer || stickToBottom) return;
		const distance =
			scrollContainer.scrollHeight - scrollContainer.clientHeight - scrollContainer.scrollTop;
		if (distance < REENGAGE_PX) stickToBottom = true;
	}

	function handleWheel(e: WheelEvent) {
		// Any upward wheel = user wants to read above. Disengage immediately.
		// Downward wheel is harmless: scroll handler will re-engage when they
		// reach the bottom.
		if (e.deltaY < 0) stickToBottom = false;
	}

	// Conversation switch: always start at the bottom of the freshly-loaded history,
	// regardless of where stickiness was left in the previous conversation.
	$effect(() => {
		void conversationId;
		stickToBottom = true;
	});

	// Auto-follow via ResizeObserver — fires on every height change of the
	// inner content (text deltas, tool inputs/results, typewriter wraps, new
	// blocks) OR the container itself (suggestions appearing after a turn
	// finishes shrinks .messages, viewport resizes). Both can move the
	// bottom; observing just one of them leaves the other class of change
	// unhandled. Direct `scrollTop = scrollHeight` snaps cleanly — using
	// `behavior: 'smooth'` here would race with subsequent fires and land
	// on stale targets.
	$effect(() => {
		if (!messagesInner || !scrollContainer) return;
		const container = scrollContainer;
		const ro = new ResizeObserver(() => {
			if (stickToBottom) {
				container.scrollTop = container.scrollHeight;
			}
		});
		ro.observe(messagesInner);
		ro.observe(container);
		return () => ro.disconnect();
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
		<div class="messages" bind:this={scrollContainer} onscroll={handleScroll} onwheel={handleWheel}>
			<div class="messages-inner" bind:this={messagesInner}>
				{#each messages as msg (msg.id)}
					<TurnBubble message={msg} {settings} />
				{/each}

				{#if liveTurn}
					<TurnBubble {liveTurn} isLive={true} {settings} />
				{/if}
			</div>
		</div>

		<MessageInput
			bind:this={messageInput}
			{isStreaming}
			disabled={wsStatus !== 'connected'}
			{suggestions}
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
		padding: 28px 0 8px;
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
		gap: 10px;
	}

	.empty-icon {
		color: var(--text-dim);
		margin-bottom: 6px;
		opacity: 0.6;
	}

	.empty-state h2 {
		font-family: var(--font-display);
		font-size: 1.625rem;
		font-weight: 500;
		font-style: italic;
		color: var(--text);
		letter-spacing: -0.02em;
		font-optical-sizing: auto;
	}

	.empty-state p {
		font-size: 0.9375rem;
		color: var(--text-muted);
	}

</style>
