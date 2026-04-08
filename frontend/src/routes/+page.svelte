<script lang="ts">
	import { onMount } from 'svelte';
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

		wsClient?.disconnect();
		wsClient = null;
		liveTurn = null;
		isStreaming = false;

		activeConversationId = id;
		messages = await getMessages(id);

		const client = createWsClient(id, handleWsMessage);
		client.setOnStatusChange((s) => (wsStatus = s));
		client.setOnDisconnect(() => {
			// Reset streaming state on unexpected disconnect
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

	async function handleSendMessage(content: string, files: File[] = []) {
		if (!wsClient || isStreaming || !activeConversationId) return;

		// Upload files first
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
		liveTurn = { thinking: [], tool_calls: [], text: '' };

		wsClient.send(content || `[Attached: ${files.map(f => f.name).join(', ')}]`, attachmentIds);
	}

	function handleInterrupt() {
		wsClient?.interrupt();
	}

	function handleWsMessage(msg: WsMessage) {
		// Handle background task results (arrive after turn completes)
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
		{messages}
		{liveTurn}
		{isStreaming}
		{wsStatus}
		{settings}
		{suggestions}
		onSend={handleSendMessage}
		onInterrupt={handleInterrupt}
		onSuggestionClick={(q) => handleSendMessage(q)}
	/>
{:else}
	<Login onLogin={handleLogin} />
{/if}
