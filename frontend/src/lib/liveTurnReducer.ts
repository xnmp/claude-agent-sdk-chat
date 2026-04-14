/**
 * Pure reducer for processing WebSocket messages into LiveTurn state.
 * No Svelte dependency — testable in isolation.
 *
 * Blocks accumulate in arrival order: text → tool → text → tool → text
 * stays as five separate blocks, preserving the model's narrative.
 */

import type { Block, LiveTurn, QuestionBlock, ToolCallBlock, WsMessage } from './types';

const ASK_TOOL_NAME = 'mcp__askuser__ask';

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

function mapQuestionBlock(
	blocks: Block[],
	tool_use_id: string,
	fn: (q: QuestionBlock) => QuestionBlock
): Block[] {
	return blocks.map((b) =>
		b.kind === 'question' && b.tool_use_id === tool_use_id ? fn(b) : b
	);
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
			if (msg.name === ASK_TOOL_NAME) {
				// Render askuser tool calls as interactive question blocks
				// instead of generic tool cards. Question text and options
				// arrive in the paired tool_input message.
				return {
					kind: 'update',
					turn: {
						...turn,
						blocks: [
							...turn.blocks,
							{
								kind: 'question',
								tool_use_id: msg.id,
								question: '',
								options: [],
								answered: false,
								selected: null
							}
						]
					}
				};
			}
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

		case 'tool_input': {
			// If this input belongs to a question block, fill in question/options.
			const targetsQuestion = turn.blocks.some(
				(b) => b.kind === 'question' && b.tool_use_id === msg.tool_use_id
			);
			if (targetsQuestion) {
				const question =
					typeof msg.input.question === 'string' ? msg.input.question : '';
				const optionsRaw = msg.input.options;
				const options = Array.isArray(optionsRaw)
					? (optionsRaw as unknown[]).filter(
							(o): o is string => typeof o === 'string'
						)
					: [];
				return {
					kind: 'update',
					turn: {
						...turn,
						blocks: mapQuestionBlock(turn.blocks, msg.tool_use_id, (q) => ({
							...q,
							question,
							options
						}))
					}
				};
			}
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
		}

		case 'tool_result': {
			const targetsQuestion = turn.blocks.some(
				(b) => b.kind === 'question' && b.tool_use_id === msg.tool_use_id
			);
			if (targetsQuestion) {
				return {
					kind: 'update',
					turn: {
						...turn,
						blocks: mapQuestionBlock(turn.blocks, msg.tool_use_id, (q) => ({
							...q,
							answered: true,
							selected: q.selected ?? msg.content
						}))
					}
				};
			}
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
		}

		case 'assistant_text':
			// Non-streaming path (tests, legacy fallback): mark as fully revealed
			// so there's no fake typewriter replay when the data arrives all at once.
			return {
				kind: 'update',
				turn: {
					...turn,
					blocks: [
						...turn.blocks,
						{ kind: 'text', text: msg.text, revealed: msg.text.length }
					]
				}
			};

		case 'text_block_start':
			// Open an empty text block for the streaming path. The typewriter
			// ticker in +page.svelte advances `revealed` toward `text.length`
			// independently of how fast the deltas arrive.
			return {
				kind: 'update',
				turn: {
					...turn,
					blocks: [...turn.blocks, { kind: 'text', text: '', revealed: 0 }]
				}
			};

		case 'text_delta': {
			// Append to the last block if it's still a text block. Leave
			// `revealed` untouched — the ticker owns that cursor.
			const last = turn.blocks[turn.blocks.length - 1];
			if (last && last.kind === 'text') {
				return {
					kind: 'update',
					turn: {
						...turn,
						blocks: [
							...turn.blocks.slice(0, -1),
							{ ...last, text: last.text + msg.text }
						]
					}
				};
			}
			// Defensive: delta arrived without a paired start. Open a fresh
			// block with revealed=0 so the ticker reveals it progressively.
			return {
				kind: 'update',
				turn: {
					...turn,
					blocks: [
						...turn.blocks,
						{ kind: 'text', text: msg.text, revealed: 0 }
					]
				}
			};
		}

		case 'thinking_block_start':
			return {
				kind: 'update',
				turn: {
					...turn,
					blocks: [...turn.blocks, { kind: 'thinking', thinking: '', signature: '' }]
				}
			};

		case 'thinking_delta': {
			const last = turn.blocks[turn.blocks.length - 1];
			if (last && last.kind === 'thinking') {
				return {
					kind: 'update',
					turn: {
						...turn,
						blocks: [
							...turn.blocks.slice(0, -1),
							{ ...last, thinking: last.thinking + msg.thinking }
						]
					}
				};
			}
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
		}

		case 'result':
			return { kind: 'finalize', turn };

		case 'error':
			return { kind: 'error' };

		default:
			return { kind: 'noop' };
	}
}
