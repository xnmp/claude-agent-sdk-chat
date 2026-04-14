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

// --- Block types -----------------------------------------------------------
//
// Assistant turns are an ordered sequence of blocks (text / thinking / tool
// call). The discriminator is `kind`. Use `narrowBlock(b, "text")` etc. when
// pattern-matching, so TypeScript knows which fields are available.

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

export interface TextBlock {
	kind: 'text';
	text: string;
	/**
	 * Number of characters of `text` that the typewriter has revealed so far.
	 *
	 * For streaming / just-finalized blocks this starts at 0 and is advanced
	 * by the typewriter ticker toward `text.length`. For blocks loaded from the
	 * DB (historical messages) it's set to `text.length` on load so they
	 * render instantly without a fake typewriter replay.
	 */
	revealed: number;
}

export interface ThinkingBlock extends ThinkingEntry {
	kind: 'thinking';
}

export interface ToolCallBlock extends ToolCallEntry {
	kind: 'tool_call';
}

/**
 * A user-facing multiple-choice question raised by the agent's
 * `mcp__askuser__ask` tool. Identified by the originating tool_use id so the
 * paired tool_result can mark it answered. The selected option is the
 * literal value the user clicked.
 */
export interface QuestionBlock {
	kind: 'question';
	tool_use_id: string;
	question: string;
	options: string[];
	answered: boolean;
	selected: string | null;
}

export type Block = TextBlock | ThinkingBlock | ToolCallBlock | QuestionBlock;

export interface UserContent {
	text: string;
}

export interface AssistantContent {
	blocks: Block[];
	model: string;
	usage: Record<string, number>;
	duration_ms: number;
	total_cost_usd: number;
	created_files: string[];
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
	// Complete text block — used by tests/fakes and as a non-streaming fallback.
	| { type: 'assistant_text'; text: string; message_id: string }
	// Streaming text/thinking. The block_start event opens an empty block;
	// each *_delta event appends to the most recently opened block.
	| { type: 'text_block_start'; block_index: number; message_id: string }
	| { type: 'text_delta'; text: string; block_index: number; message_id: string }
	| { type: 'thinking_block_start'; block_index: number; message_id: string }
	| { type: 'thinking_delta'; thinking: string; block_index: number; message_id: string }
	| {
			type: 'result';
			session_id: string;
			duration_ms: number;
			total_cost_usd: number | null;
			num_turns: number;
			is_error: boolean;
			created_files: string[];
		}
	| { type: 'error'; message: string }
	| { type: 'suggestions'; questions: string[] }
	| { type: 'title_update'; title: string };

// Live turn being streamed (not yet persisted).
// Mirrors AssistantContent's block-list shape so finalization is just a copy.
export interface LiveTurn {
	startedAt: number; // Date.now() when streaming began
	blocks: Block[];
}
