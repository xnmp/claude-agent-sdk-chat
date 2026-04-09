<script lang="ts">
	import { onMount, tick } from 'svelte';
	import Sidebar from '../components/Sidebar.svelte';
	import ChatView from '../components/ChatView.svelte';
	import Login from '../components/Login.svelte';
	import type { Conversation, Message, LiveTurn, WsMessage, AssistantContent, User } from '$lib/types';
	import { listConversations, createConversation, getMessages, deleteConversation, login, uploadFile } from '$lib/api';
	import { createWsClient, type WsClient, type WsStatus } from '$lib/ws';
	import { processWsMessage } from '$lib/liveTurnReducer';
	import { loadSettings, saveSettings, applyTheme, type Settings } from '$lib/settings';

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
				turn: liveTurn ?? { startedAt: Date.now(), thinking: [], tool_calls: [], text: '' },
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
		messages = await getMessages(id);

		// Restore from background stream if one exists
		const bg = bgStreams.get(id);
		if (bg) {
			if (bg.done) {
				// Turn completed in background — reload messages
				messages = await getMessages(id);
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

	async function handleNewChat() {
		const conv = await createConversation();
		conversations = [conv, ...conversations];
		await selectConversation(conv.id);
		await tick();
		chatView?.focusInput();
	}

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
		liveTurn = { startedAt: Date.now(), thinking: [], tool_calls: [], text: '' };

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
					thinking: turn.thinking,
					tool_calls: turn.tool_calls,
					text: turn.text,
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
				break;

			case 'finalize':
				if (msg.type === 'result') {
					const assistantMsg: Message = {
						id: crypto.randomUUID(),
						conversation_id: activeConversationId!,
						role: 'assistant',
						content: {
							thinking: action.turn.thinking,
							tool_calls: action.turn.tool_calls,
							text: action.turn.text,
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
		onSend={handleSendMessage}
		onInterrupt={handleInterrupt}
	/>
{:else}
	<Login onLogin={handleLogin} />
{/if}
