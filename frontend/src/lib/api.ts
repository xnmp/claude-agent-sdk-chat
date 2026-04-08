import type { Conversation, Message, User } from './types';

const BASE = 'http://localhost:8000/api';

export class ApiError extends Error {
	constructor(
		public status: number,
		message: string
	) {
		super(message);
	}
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
	const res = await fetch(url, options);
	if (!res.ok) {
		const text = await res.text().catch(() => res.statusText);
		throw new ApiError(res.status, text);
	}
	return res.json();
}

export async function login(email: string, displayName?: string): Promise<User> {
	return request(`${BASE}/auth/login`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ email, display_name: displayName ?? null })
	});
}

export async function listConversations(): Promise<Conversation[]> {
	const data = await request<{ conversations: Conversation[] }>(`${BASE}/conversations`);
	return data.conversations;
}

export async function createConversation(title?: string): Promise<Conversation> {
	return request(`${BASE}/conversations`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ title: title ?? null })
	});
}

export async function getMessages(conversationId: string): Promise<Message[]> {
	const data = await request<{ messages: Message[] }>(
		`${BASE}/conversations/${conversationId}/messages`
	);
	return data.messages;
}

export async function deleteConversation(conversationId: string): Promise<void> {
	await request(`${BASE}/conversations/${conversationId}`, { method: 'DELETE' });
}

export async function updateConversationTitle(
	conversationId: string,
	title: string
): Promise<void> {
	await request(`${BASE}/conversations/${conversationId}`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ title })
	});
}
