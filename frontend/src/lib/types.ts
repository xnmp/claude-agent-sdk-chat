export interface User {
	id: string;
	email: string;
	display_name: string | null;
}

export interface Conversation {
	id: string;
	title: string | null;
	sdk_session_id: string | null;
	created_at: string;
	updated_at: string;
}

export interface ThinkingEntry {
	thinking: string;
	signature: string;
}

export interface ToolCallEntry {
	id: string;
	name: string;
	input: Record<string, unknown>;
	result: string | null;
	is_error: boolean | null;
}

export interface UserContent {
	text: string;
}

export interface AssistantContent {
	thinking: ThinkingEntry[];
	tool_calls: ToolCallEntry[];
	text: string;
	model: string;
	usage: Record<string, number>;
	duration_ms: number;
	total_cost_usd: number;
}

export interface Message {
	id: string;
	conversation_id: string;
	role: 'user' | 'assistant';
	content: UserContent | AssistantContent;
	created_at: string;
}

// WebSocket message types (server → client)
export type WsMessage =
	| { type: 'thinking'; thinking: string; message_id: string }
	| { type: 'tool_use'; id: string; name: string; message_id: string }
	| { type: 'tool_input'; tool_use_id: string; input: Record<string, unknown> }
	| { type: 'tool_result'; tool_use_id: string; content: string; is_error: boolean }
	| { type: 'assistant_text'; text: string; message_id: string }
	| {
			type: 'result';
			session_id: string;
			duration_ms: number;
			total_cost_usd: number | null;
			num_turns: number;
			is_error: boolean;
		}
	| { type: 'error'; message: string };

// Live turn being streamed (not yet persisted)
export interface LiveTurn {
	thinking: ThinkingEntry[];
	tool_calls: ToolCallEntry[];
	text: string;
}
