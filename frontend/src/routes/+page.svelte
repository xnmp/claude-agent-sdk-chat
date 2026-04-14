<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import Sidebar from '../components/Sidebar.svelte';
	import ChatView from '../components/ChatView.svelte';
	import Login from '../components/Login.svelte';
	import type { Block, Conversation, Message, LiveTurn, WsMessage, AssistantContent, User } from '$lib/types';
	import { listConversations, createConversation, getMessages, deleteConversation, login, uploadFile, updateConversationTitle } from '$lib/api';
	import { createWsClient, type WsClient, type WsStatus } from '$lib/ws';
	import { processWsMessage } from '$lib/liveTurnReducer';
	import { loadSettings, saveSettings, applyTheme, type Settings } from '$lib/settings';
	import { createTypewriter } from '$lib/typewriter';

	let currentUser = $state<User | null>(null);
	let settings = $state<Settings>(loadSettings());
	let conversations = $state<Conversation[]>([]);
	let activeConversationId = $state<string | null>(null);
	let messages = $state<Message[]>([]);
	let isStreaming = $state(false);
	let liveTurn = $state<LiveTurn | null>(null);
	let wsClient = $state<WsClient | null>(null);
	let wsStatus = $state<WsStatus>('disconnected');
	let suggestions = $state<string[]>([]);
	let chatView: ChatView | undefined = $state();

	// Per-conversation background streaming state
	interface BgStream { turn: LiveTurn; suggestions: string[]; ws: WsClient; done: boolean }
	const bgStreams = new Map<string, BgStream>();

	// -- Typewriter ticker --------------------------------------------------
	//
	// Every text block (live or just-finalized) carries a `revealed` cursor
	// separately from its `text`. SDK deltas grow `text`; the typewriter
	// (defined in $lib/typewriter) is the ONLY writer of `revealed`.
	//
	// Because the cursor lives on the block itself, finalize doesn't need
	// any special handling: the persisted message's blocks are the same
	// references we've been advancing, and the ticker keeps going until
	// they're drained.

	const typewriter = createTypewriter();
	let typewriterFrameId: number | null = null;
	let typewriterLastTime = 0;

	function typewriterTick(now: number) {
		const dt = Math.min(100, Math.max(0, now - typewriterLastTime));
		typewriterLastTime = now;

		let anyProgress = false;

		if (liveTurn) {
			if (typewriter.advanceBlocks(liveTurn.blocks, dt)) anyProgress = true;
		}
		// Also drain any freshly-finalized messages whose cursors still have
		// work to do. Once `revealed === text.length` for all blocks they
		// drop out of this loop naturally.
		for (const msg of messages) {
			if (msg.role !== 'assistant') continue;
			const content = msg.content as AssistantContent;
			if (typewriter.advanceBlocks(content.blocks as Block[], dt))
				anyProgress = true;
		}

		if (anyProgress) {
			typewriterFrameId = requestAnimationFrame(typewriterTick);
		} else {
			typewriterFrameId = null;
		}
	}

	function kickTypewriter() {
		if (typewriterFrameId !== null) return;
		typewriterLastTime = performance.now();
		typewriterFrameId = requestAnimationFrame(typewriterTick);
	}

	/**
	 * Historical messages loaded from the API should render instantly — no
	 * fake typewriter replay for text the user already saw. Mark every text
	 * block as fully revealed up-front.
	 */
	function normalizeLoadedMessages(msgs: Message[]): Message[] {
		return msgs.map((m) => {
			if (m.role !== 'assistant') return m;
			const content = m.content as AssistantContent;
			const blocks = content.blocks.map((b) =>
				b.kind === 'text' ? { ...b, revealed: b.text.length } : b
			);
			return { ...m, content: { ...content, blocks } };
		});
	}

	onDestroy(() => {
		if (typewriterFrameId !== null) {
			cancelAnimationFrame(typewriterFrameId);
			typewriterFrameId = null;
		}
	});

	onMount(() => {
		applyTheme(settings.theme);
		const stored = localStorage.getItem('user');
		if (stored) {
			currentUser = JSON.parse(stored);
			loadConversations();
		}
	});

	function handleSettingsChange(newSettings: Settings) {
		settings = newSettings;
		saveSettings(settings);
		applyTheme(settings.theme);
	}

	async function handleLogin(email: string, displayName?: string) {
		const user = await login(email, displayName);
		localStorage.setItem('user', JSON.stringify(user));
		currentUser = user;
		loadConversations();
	}

	function handleLogout() {
		localStorage.removeItem('user');
		currentUser = null;
		conversations = [];
		activeConversationId = null;
		messages = [];
		wsClient?.disconnect();
		wsClient = null;
	}

	async function loadConversations() {
		conversations = await listConversations();
	}

	async function selectConversation(id: string) {
		if (activeConversationId === id) return;

		if (isStreaming && wsClient && activeConversationId) {
			// Stash state and keep WS alive in background
			const convId = activeConversationId;
			const bg: BgStream = {
				turn: liveTurn ?? { startedAt: Date.now(), blocks: [] },
				suggestions,
				ws: wsClient,
				done: false,
			};
			bgStreams.set(convId, bg);

			// Rewire WS callbacks to update bg state instead of UI
			const bgWs = wsClient;
			bgWs.setOnStatusChange(() => {});
			bgWs.setOnDisconnect(() => {
				bg.done = true;
			});
			// Note: the WS will keep calling handleWsMessage, which checks
			// activeConversationId. Events for the old conversation will be
			// routed to bgStreams in handleWsMessage below.
		} else {
			wsClient?.disconnect();
		}

		wsClient = null;
		liveTurn = null;
		isStreaming = false;
		suggestions = [];

		activeConversationId = id;
		messages = normalizeLoadedMessages(await getMessages(id));

		// Restore from background stream if one exists
		const bg = bgStreams.get(id);
		if (bg) {
			if (bg.done) {
				// Turn completed in background — reload messages
				messages = normalizeLoadedMessages(await getMessages(id));
				suggestions = bg.suggestions;
				bg.ws.disconnect();
				bgStreams.delete(id);
			} else {
				// Still streaming — restore live state and reattach WS
				liveTurn = bg.turn;
				isStreaming = true;
				suggestions = bg.suggestions;
				wsClient = bg.ws;
				wsStatus = 'connected';
				bgStreams.delete(id);
				return; // Don't create a new WS
			}
		}

		const client = createWsClient(id, _makeWsHandler(id));
		client.setOnStatusChange((s) => (wsStatus = s));
		client.setOnDisconnect(() => {
			if (isStreaming) {
				isStreaming = false;
				liveTurn = null;
			}
		});
		client.connect();
		wsClient = client;
	}

	let pendingNewChatFocus = $state(false);

	async function handleNewChat() {
		const conv = await createConversation();
		conversations = [conv, ...conversations];
		pendingNewChatFocus = true;
		await selectConversation(conv.id);
	}

	// Focus the input once the new conversation's WS is actually connected —
	// until then the textarea is disabled and focus() is a no-op.
	$effect(() => {
		if (pendingNewChatFocus && wsStatus === 'connected') {
			pendingNewChatFocus = false;
			chatView?.focusInput();
		}
	});

	async function handleDeleteConversation(id: string) {
		await deleteConversation(id);
		const bg = bgStreams.get(id);
		if (bg) { bg.ws.disconnect(); bgStreams.delete(id); }
		conversations = conversations.filter((c) => c.id !== id);
		if (activeConversationId === id) {
			activeConversationId = null;
			messages = [];
			wsClient?.disconnect();
			wsClient = null;
		}
	}

	async function handleRenameConversation(id: string, title: string) {
		// Optimistic local update — the PATCH below is the source of truth.
		conversations = conversations.map((c) =>
			c.id === id ? { ...c, title } : c
		);
		try {
			await updateConversationTitle(id, title);
		} catch {
			// On failure, refresh from server to surface the actual title.
			loadConversations();
		}
	}

	async function handleSendMessage(content: string, files: File[] = []) {
		if (!wsClient || isStreaming || !activeConversationId) return;

		const attachmentIds: string[] = [];
		for (const file of files) {
			try {
				const result = await uploadFile(activeConversationId, file);
				attachmentIds.push(result.id);
			} catch {
				// TODO: surface upload errors to UI
			}
		}

		const displayText = files.length > 0
			? `${content}${content ? '\n' : ''}[${files.map(f => f.name).join(', ')}]`
			: content;

		const userMsg: Message = {
			id: crypto.randomUUID(),
			conversation_id: activeConversationId,
			role: 'user',
			content: { text: displayText },
			created_at: new Date().toISOString()
		};
		messages = [...messages, userMsg];

		isStreaming = true;
		liveTurn = { startedAt: Date.now(), blocks: [] };

		wsClient.send(content || `[Attached: ${files.map(f => f.name).join(', ')}]`, attachmentIds);
	}

	function _makeWsHandler(convId: string): (msg: WsMessage) => void {
		return (msg: WsMessage) => {
			// If this conversation is in the background, update its bgStream
			const bg = bgStreams.get(convId);
			if (bg) {
				if (msg.type === 'suggestions') {
					bg.suggestions = msg.questions;
				} else if (msg.type === 'title_update') {
					conversations = conversations.map((c) =>
						c.id === convId ? { ...c, title: msg.title } : c
					);
				} else {
					const action = processWsMessage(msg, bg.turn);
					if (action.kind === 'update') {
						bg.turn = action.turn;
						// If user is viewing this conversation, sync to UI
						if (activeConversationId === convId) {
							liveTurn = bg.turn;
							kickTypewriter();
						}
					} else if (action.kind === 'finalize') {
						bg.done = true;
						// If user is viewing this conversation, finalize in UI
						if (activeConversationId === convId) {
							_finalizeFromBg(convId, action.turn, msg);
						}
					} else if (action.kind === 'error') {
						bg.done = true;
						if (activeConversationId === convId) {
							isStreaming = false;
							liveTurn = null;
						}
					}
				}
				return;
			}

			// Active conversation — update UI directly
			if (convId !== activeConversationId) return;
			handleWsMessage(msg);
		};
	}

	function _finalizeFromBg(convId: string, turn: LiveTurn, msg: WsMessage) {
		if (msg.type === 'result') {
			const assistantMsg: Message = {
				id: crypto.randomUUID(),
				conversation_id: convId,
				role: 'assistant',
				content: {
					blocks: turn.blocks,
					model: '',
					usage: {},
					duration_ms: msg.duration_ms,
					total_cost_usd: msg.total_cost_usd ?? 0,
					created_files: msg.created_files ?? []
				} satisfies AssistantContent,
				created_at: new Date().toISOString()
			};
			messages = [...messages, assistantMsg];
		}
		liveTurn = null;
		isStreaming = false;
		suggestions = [];
		kickTypewriter();
		const bg = bgStreams.get(convId);
		if (bg) { bg.ws.disconnect(); bgStreams.delete(convId); }
		loadConversations();
	}

	function handleInterrupt() {
		wsClient?.interrupt();
	}

	function handleWsMessage(msg: WsMessage) {
		// Route events for background conversations to their bgStream
		// The WS handler closure doesn't know which conversation it's for,
		// but we can check: if we're not streaming on the active conversation
		// but there are background streams, route to the right one.
		// However, the WS is per-conversation, so events always belong to
		// the conversation that created the WS. Since we reattach the WS
		// on restore, this handler is always for the active conversation.

		if (msg.type === 'suggestions') {
			suggestions = msg.questions;
			return;
		}
		if (msg.type === 'title_update') {
			conversations = conversations.map((c) =>
				c.id === activeConversationId ? { ...c, title: msg.title } : c
			);
			return;
		}

		const action = processWsMessage(msg, liveTurn);

		switch (action.kind) {
			case 'update':
				liveTurn = action.turn;
				// A delta just grew one of the text blocks — make sure the
				// typewriter ticker is running so the new chars get revealed.
				kickTypewriter();
				break;

			case 'finalize':
				if (msg.type === 'result') {
					// Hand the live block list directly to the persisted message.
					// The `revealed` cursors on each block carry over with their
					// current values, so the typewriter keeps draining them
					// after the live→persisted swap — no snap.
					const assistantMsg: Message = {
						id: crypto.randomUUID(),
						conversation_id: activeConversationId!,
						role: 'assistant',
						content: {
							blocks: action.turn.blocks,
							model: '',
							usage: {},
							duration_ms: msg.duration_ms,
							total_cost_usd: msg.total_cost_usd ?? 0,
							created_files: msg.created_files ?? []
						} satisfies AssistantContent,
						created_at: new Date().toISOString()
					};
					messages = [...messages, assistantMsg];
				}
				liveTurn = null;
				isStreaming = false;
				suggestions = [];
				// Keep the ticker alive to drain the block we just transferred
				// to `messages`.
				kickTypewriter();
				loadConversations();
				break;

			case 'error':
				isStreaming = false;
				liveTurn = null;
				suggestions = [];
				break;
		}
	}
</script>

{#if currentUser}
	<Sidebar
		{conversations}
		{activeConversationId}
		onSelect={selectConversation}
		onNew={handleNewChat}
		onDelete={handleDeleteConversation}
		onRename={handleRenameConversation}
		user={currentUser}
		onLogout={handleLogout}
		{settings}
		onSettingsChange={handleSettingsChange}
	/>

	<ChatView
		bind:this={chatView}
		{messages}
		{liveTurn}
		{isStreaming}
		{wsStatus}
		{settings}
		{suggestions}
		conversationId={activeConversationId}
		onSend={handleSendMessage}
		onInterrupt={handleInterrupt}
	/>
{:else}
	<Login onLogin={handleLogin} />
{/if}
