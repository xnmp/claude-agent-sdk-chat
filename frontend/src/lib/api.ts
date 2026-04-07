import type { Conversation, Message } from './types';

const BASE = 'http://localhost:8000/api';

export async function listConversations(): Promise<Conversation[]> {
	const res = await fetch(`${BASE}/conversations`);
	const data = await res.json();
	return data.conversations;
}

export async function createConversation(title?: string): Promise<Conversation> {
	const res = await fetch(`${BASE}/conversations`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ title: title ?? null })
	});
	return res.json();
}

export async function getMessages(conversationId: string): Promise<Message[]> {
	const res = await fetch(`${BASE}/conversations/${conversationId}/messages`);
	const data = await res.json();
	return data.messages;
}

export async function deleteConversation(conversationId: string): Promise<void> {
	await fetch(`${BASE}/conversations/${conversationId}`, { method: 'DELETE' });
}

export async function updateConversationTitle(
	conversationId: string,
	title: string
): Promise<void> {
	await fetch(`${BASE}/conversations/${conversationId}`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ title })
	});
}
