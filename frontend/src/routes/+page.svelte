<script lang="ts">
	import { onMount } from 'svelte';
	import Sidebar from '../components/Sidebar.svelte';
	import ChatView from '../components/ChatView.svelte';
	import Login from '../components/Login.svelte';
	import type { Conversation, Message, LiveTurn, WsMessage, AssistantContent, User } from '$lib/types';
	import { listConversations, createConversation, getMessages, deleteConversation } from '$lib/api';
	import { createWsClient, type WsClient, type WsStatus } from '$lib/ws';

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

	function handleLogin(user: User) {
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
		if (!liveTurn && msg.type !== 'result' && msg.type !== 'error') {
			liveTurn = { thinking: [], tool_calls: [], text: '' };
		}

		switch (msg.type) {
			case 'thinking':
				if (liveTurn) {
					liveTurn.thinking = [...liveTurn.thinking, { thinking: msg.thinking, signature: '' }];
				}
				break;

			case 'tool_use':
				if (liveTurn) {
					liveTurn.tool_calls = [
						...liveTurn.tool_calls,
						{ id: msg.id, name: msg.name, input: {}, result: null, is_error: null }
					];
				}
				break;

			case 'tool_input':
				if (liveTurn) {
					liveTurn.tool_calls = liveTurn.tool_calls.map((tc) =>
						tc.id === msg.tool_use_id ? { ...tc, input: msg.input } : tc
					);
				}
				break;

			case 'tool_result':
				if (liveTurn) {
					liveTurn.tool_calls = liveTurn.tool_calls.map((tc) =>
						tc.id === msg.tool_use_id
							? { ...tc, result: msg.content, is_error: msg.is_error }
							: tc
					);
				}
				break;

			case 'assistant_text':
				if (liveTurn) {
					liveTurn.text = msg.text;
				}
				break;

			case 'result': {
				if (liveTurn) {
					const assistantMsg: Message = {
						id: crypto.randomUUID(),
						conversation_id: activeConversationId!,
						role: 'assistant',
						content: {
							thinking: liveTurn.thinking,
							tool_calls: liveTurn.tool_calls,
							text: liveTurn.text,
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
			}

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
	<Login onLogin={handleLogin} />
{/if}
