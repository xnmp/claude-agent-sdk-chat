<script lang="ts">
	import { onMount } from 'svelte';
	import Sidebar from '../components/Sidebar.svelte';
	import ChatView from '../components/ChatView.svelte';
	import Login from '../components/Login.svelte';
	import type { Conversation, Message, LiveTurn, WsMessage, AssistantContent, User } from '$lib/types';
	import { listConversations, createConversation, getMessages, deleteConversation, login } from '$lib/api';
	import { createWsClient, type WsClient, type WsStatus } from '$lib/ws';
	import { processWsMessage } from '$lib/liveTurnReducer';

	let currentUser = $state<User | null>(null);
	let conversations = $state<Conversation[]>([]);
	let activeConversationId = $state<string | null>(null);
	let messages = $state<Message[]>([]);
	let isStreaming = $state(false);
	let liveTurn = $state<LiveTurn | null>(null);
	let wsClient = $state<WsClient | null>(null);
	let wsStatus = $state<WsStatus>('disconnected');

	onMount(() => {
		const stored = localStorage.getItem('user');
		if (stored) {
			currentUser = JSON.parse(stored);
			loadConversations();
		}
	});

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

		wsClient?.disconnect();
		wsClient = null;
		liveTurn = null;
		isStreaming = false;

		activeConversationId = id;
		messages = await getMessages(id);

		const client = createWsClient(id, handleWsMessage);
		client.setOnStatusChange((s) => (wsStatus = s));
		client.connect();
		wsClient = client;
	}

	async function handleNewChat() {
		const conv = await createConversation();
		conversations = [conv, ...conversations];
		await selectConversation(conv.id);
	}

	async function handleDeleteConversation(id: string) {
		await deleteConversation(id);
		conversations = conversations.filter((c) => c.id !== id);
		if (activeConversationId === id) {
			activeConversationId = null;
			messages = [];
			wsClient?.disconnect();
			wsClient = null;
		}
	}

	function handleSendMessage(content: string) {
		if (!wsClient || isStreaming) return;

		const userMsg: Message = {
			id: crypto.randomUUID(),
			conversation_id: activeConversationId!,
			role: 'user',
			content: { text: content },
			created_at: new Date().toISOString()
		};
		messages = [...messages, userMsg];

		isStreaming = true;
		liveTurn = { thinking: [], tool_calls: [], text: '' };

		wsClient.send(content);
	}

	function handleInterrupt() {
		wsClient?.interrupt();
	}

	function handleWsMessage(msg: WsMessage) {
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
							total_cost_usd: msg.total_cost_usd ?? 0
						} satisfies AssistantContent,
						created_at: new Date().toISOString()
					};
					messages = [...messages, assistantMsg];
				}
				liveTurn = null;
				isStreaming = false;
				loadConversations();
				break;

			case 'error':
				isStreaming = false;
				liveTurn = null;
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
	/>

	<ChatView
		{messages}
		{liveTurn}
		{isStreaming}
		{wsStatus}
		onSend={handleSendMessage}
		onInterrupt={handleInterrupt}
	/>
{:else}
	<Login onSubmit={handleLogin} />
{/if}
