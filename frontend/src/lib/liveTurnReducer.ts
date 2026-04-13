/**
 * Pure reducer for processing WebSocket messages into LiveTurn state.
 * No Svelte dependency — testable in isolation.
 *
 * Blocks accumulate in arrival order: text → tool → text → tool → text
 * stays as five separate blocks, preserving the model's narrative.
 */

import type { Block, LiveTurn, ToolCallBlock, WsMessage } from './types';

export type TurnAction =
	| { kind: 'update'; turn: LiveTurn }
	| { kind: 'finalize'; turn: LiveTurn }
	| { kind: 'error' }
	| { kind: 'noop' };

function emptyTurn(): LiveTurn {
	return { startedAt: Date.now(), blocks: [] };
}

function mapBlocks(blocks: Block[], id: string, fn: (tc: ToolCallBlock) => ToolCallBlock): Block[] {
	return blocks.map((b) => (b.kind === 'tool_call' && b.id === id ? fn(b) : b));
}

/**
 * Process a WebSocket message against the current live turn.
 * Returns an action describing what happened — the caller decides
 * how to apply it to reactive state.
 */
export function processWsMessage(msg: WsMessage, current: LiveTurn | null): TurnAction {
	const turn: LiveTurn = current ?? emptyTurn();

	switch (msg.type) {
		case 'thinking':
			return {
				kind: 'update',
				turn: {
					...turn,
					blocks: [
						...turn.blocks,
						{ kind: 'thinking', thinking: msg.thinking, signature: '' }
					]
				}
			};

		case 'tool_use':
			return {
				kind: 'update',
				turn: {
					...turn,
					blocks: [
						...turn.blocks,
						{
							kind: 'tool_call',
							id: msg.id,
							name: msg.name,
							input: {},
							result: null,
							is_error: null
						}
					]
				}
			};

		case 'tool_input':
			return {
				kind: 'update',
				turn: {
					...turn,
					blocks: mapBlocks(turn.blocks, msg.tool_use_id, (tc) => ({
						...tc,
						input: msg.input
					}))
				}
			};

		case 'tool_result':
			return {
				kind: 'update',
				turn: {
					...turn,
					blocks: mapBlocks(turn.blocks, msg.tool_use_id, (tc) => ({
						...tc,
						result: msg.content,
						is_error: msg.is_error
					}))
				}
			};

		case 'assistant_text':
			return {
				kind: 'update',
				turn: {
					...turn,
					blocks: [...turn.blocks, { kind: 'text', text: msg.text }]
				}
			};

		case 'result':
			return { kind: 'finalize', turn };

		case 'error':
			return { kind: 'error' };

		default:
			return { kind: 'noop' };
	}
}
