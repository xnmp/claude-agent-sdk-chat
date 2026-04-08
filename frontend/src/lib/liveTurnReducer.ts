/**
 * Pure reducer for processing WebSocket messages into LiveTurn state.
 * No Svelte dependency — testable in isolation.
 */

import type { LiveTurn, WsMessage } from './types';

export type TurnAction =
	| { kind: 'update'; turn: LiveTurn }
	| { kind: 'finalize'; turn: LiveTurn }
	| { kind: 'error' }
	| { kind: 'noop' };

/**
 * Process a WebSocket message against the current live turn.
 * Returns an action describing what happened — the caller decides
 * how to apply it to reactive state.
 */
export function processWsMessage(msg: WsMessage, current: LiveTurn | null): TurnAction {
	const turn: LiveTurn = current ?? { thinking: [], tool_calls: [], text: '' };

	switch (msg.type) {
		case 'thinking':
			return {
				kind: 'update',
				turn: {
					...turn,
					thinking: [...turn.thinking, { thinking: msg.thinking, signature: '' }]
				}
			};

		case 'tool_use':
			return {
				kind: 'update',
				turn: {
					...turn,
					tool_calls: [
						...turn.tool_calls,
						{ id: msg.id, name: msg.name, input: {}, result: null, is_error: null }
					]
				}
			};

		case 'tool_input':
			return {
				kind: 'update',
				turn: {
					...turn,
					tool_calls: turn.tool_calls.map((tc) =>
						tc.id === msg.tool_use_id ? { ...tc, input: msg.input } : tc
					)
				}
			};

		case 'tool_result':
			return {
				kind: 'update',
				turn: {
					...turn,
					tool_calls: turn.tool_calls.map((tc) =>
						tc.id === msg.tool_use_id
							? { ...tc, result: msg.content, is_error: msg.is_error }
							: tc
					)
				}
			};

		case 'assistant_text':
			return {
				kind: 'update',
				turn: { ...turn, text: msg.text }
			};

		case 'result':
			return { kind: 'finalize', turn };

		case 'error':
			return { kind: 'error' };
	}
}
