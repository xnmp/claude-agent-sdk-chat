import { describe, it, expect } from 'vitest';
import { processWsMessage } from '$lib/liveTurnReducer';
import type { LiveTurn, ToolCallBlock, WsMessage } from '$lib/types';

function emptyTurn(): LiveTurn {
	return { startedAt: Date.now(), blocks: [] };
}

function kinds(turn: LiveTurn): string[] {
	return turn.blocks.map((b) => b.kind);
}

describe('processWsMessage', () => {
	it('creates turn from null on thinking message', () => {
		const msg: WsMessage = { type: 'thinking', thinking: 'hmm', message_id: 'm1' };
		const action = processWsMessage(msg, null);

		expect(action.kind).toBe('update');
		if (action.kind === 'update') {
			expect(kinds(action.turn)).toEqual(['thinking']);
			const block = action.turn.blocks[0];
			if (block.kind === 'thinking') {
				expect(block.thinking).toBe('hmm');
			}
		}
	});

	it('appends thinking blocks to existing turn', () => {
		const turn = emptyTurn();
		turn.blocks = [{ kind: 'thinking', thinking: 'first', signature: '' }];

		const msg: WsMessage = { type: 'thinking', thinking: 'second', message_id: 'm1' };
		const action = processWsMessage(msg, turn);

		if (action.kind === 'update') {
			expect(kinds(action.turn)).toEqual(['thinking', 'thinking']);
			const second = action.turn.blocks[1];
			if (second.kind === 'thinking') {
				expect(second.thinking).toBe('second');
			}
		}
	});

	it('appends tool_use as a tool_call block', () => {
		const msg: WsMessage = { type: 'tool_use', id: 't1', name: 'Read', message_id: 'm1' };
		const action = processWsMessage(msg, emptyTurn());

		if (action.kind === 'update') {
			expect(kinds(action.turn)).toEqual(['tool_call']);
			const block = action.turn.blocks[0] as ToolCallBlock;
			expect(block.id).toBe('t1');
			expect(block.name).toBe('Read');
		}
	});

	it('updates tool_call input on tool_input', () => {
		const turn = emptyTurn();
		turn.blocks = [
			{ kind: 'tool_call', id: 't1', name: 'Read', input: {}, result: null, is_error: null }
		];

		const msg: WsMessage = { type: 'tool_input', tool_use_id: 't1', input: { path: '/tmp' } };
		const action = processWsMessage(msg, turn);

		if (action.kind === 'update') {
			const block = action.turn.blocks[0] as ToolCallBlock;
			expect(block.input).toEqual({ path: '/tmp' });
		}
	});

	it('updates tool_call result on tool_result', () => {
		const turn = emptyTurn();
		turn.blocks = [
			{ kind: 'tool_call', id: 't1', name: 'Read', input: {}, result: null, is_error: null }
		];

		const msg: WsMessage = {
			type: 'tool_result',
			tool_use_id: 't1',
			content: 'file contents',
			is_error: false
		};
		const action = processWsMessage(msg, turn);

		if (action.kind === 'update') {
			const block = action.turn.blocks[0] as ToolCallBlock;
			expect(block.result).toBe('file contents');
			expect(block.is_error).toBe(false);
		}
	});

	it('appends a fully-revealed text block on assistant_text', () => {
		// The non-streaming path already has the full text on arrival, so the
		// reducer sets `revealed` to the text length — no typewriter replay.
		const msg: WsMessage = { type: 'assistant_text', text: 'Hello!', message_id: 'm1' };
		const action = processWsMessage(msg, emptyTurn());

		if (action.kind === 'update') {
			expect(kinds(action.turn)).toEqual(['text']);
			const block = action.turn.blocks[0];
			if (block.kind === 'text') {
				expect(block.text).toBe('Hello!');
				expect(block.revealed).toBe('Hello!'.length);
			}
		}
	});

	it('opens streaming text_block_start with revealed=0', () => {
		const action = processWsMessage(
			{ type: 'text_block_start', block_index: 0, message_id: 'm1' },
			emptyTurn()
		);
		if (action.kind === 'update') {
			const block = action.turn.blocks[0];
			if (block.kind === 'text') {
				// A fresh streaming block is completely un-revealed — the ticker
				// in +page.svelte owns the advance from here.
				expect(block.revealed).toBe(0);
			}
		}
	});

	it('text_delta grows text but leaves revealed untouched', () => {
		let turn: LiveTurn | null = emptyTurn();
		turn = (
			processWsMessage(
				{ type: 'text_block_start', block_index: 0, message_id: 'm1' },
				turn
			) as { turn: LiveTurn }
		).turn;
		turn = (
			processWsMessage(
				{ type: 'text_delta', text: 'Hello world', block_index: 0, message_id: 'm1' },
				turn
			) as { turn: LiveTurn }
		).turn;

		const block = turn.blocks[0];
		if (block.kind === 'text') {
			expect(block.text).toBe('Hello world');
			// Reducer must not touch revealed — the ticker owns that cursor.
			expect(block.revealed).toBe(0);
		}
	});

	it('preserves multiple text blocks instead of overwriting', () => {
		// Regression: previously a second TextEvent overwrote the first, losing
		// the model's narrative ("let me check…" → tool → "now I'll…" became
		// just "now I'll…"). The reducer must append.
		let turn: LiveTurn | null = emptyTurn();
		turn = (
			processWsMessage({ type: 'assistant_text', text: 'partial', message_id: 'm1' }, turn) as {
				turn: LiveTurn;
			}
		).turn;
		turn = (
			processWsMessage(
				{ type: 'assistant_text', text: 'continued', message_id: 'm2' },
				turn
			) as { turn: LiveTurn }
		).turn;

		expect(kinds(turn)).toEqual(['text', 'text']);
		const texts = turn.blocks
			.filter((b) => b.kind === 'text')
			.map((b) => (b as { text: string }).text);
		expect(texts).toEqual(['partial', 'continued']);
	});

	it('preserves interleaved text and tool_call ordering', () => {
		// text → tool_use → tool_result → text — five messages, three blocks.
		let turn: LiveTurn | null = emptyTurn();
		const msgs: WsMessage[] = [
			{ type: 'assistant_text', text: 'let me check', message_id: 'm1' },
			{ type: 'tool_use', id: 't1', name: 'Read', message_id: 'm1' },
			{ type: 'tool_input', tool_use_id: 't1', input: { path: '/x' } },
			{ type: 'tool_result', tool_use_id: 't1', content: 'ok', is_error: false },
			{ type: 'assistant_text', text: 'done', message_id: 'm2' }
		];
		for (const m of msgs) {
			turn = (processWsMessage(m, turn) as { turn: LiveTurn }).turn;
		}
		expect(kinds(turn)).toEqual(['text', 'tool_call', 'text']);
		const tool = turn.blocks[1] as ToolCallBlock;
		expect(tool.input).toEqual({ path: '/x' });
		expect(tool.result).toBe('ok');
	});

	it('opens an empty text block on text_block_start', () => {
		const action = processWsMessage(
			{ type: 'text_block_start', block_index: 0, message_id: 'm1' },
			emptyTurn()
		);
		if (action.kind === 'update') {
			expect(kinds(action.turn)).toEqual(['text']);
			const block = action.turn.blocks[0];
			if (block.kind === 'text') {
				expect(block.text).toBe('');
			}
		}
	});

	it('grows the open text block with text_delta', () => {
		// Simulate the streaming sequence: start, then several deltas.
		let turn: LiveTurn | null = emptyTurn();
		turn = (
			processWsMessage(
				{ type: 'text_block_start', block_index: 0, message_id: 'm1' },
				turn
			) as { turn: LiveTurn }
		).turn;
		for (const chunk of ['He', 'llo', ', world!']) {
			turn = (
				processWsMessage(
					{ type: 'text_delta', text: chunk, block_index: 0, message_id: 'm1' },
					turn
				) as { turn: LiveTurn }
			).turn;
		}
		expect(kinds(turn)).toEqual(['text']);
		const block = turn.blocks[0];
		if (block.kind === 'text') {
			expect(block.text).toBe('Hello, world!');
		}
	});

	it('text_delta opens a new block when previous block is not text', () => {
		// Defensive: orphaned delta after a tool_call should still capture text.
		let turn: LiveTurn | null = emptyTurn();
		turn = (
			processWsMessage(
				{ type: 'tool_use', id: 't1', name: 'Read', message_id: 'm1' },
				turn
			) as { turn: LiveTurn }
		).turn;
		turn = (
			processWsMessage(
				{ type: 'text_delta', text: 'orphan', block_index: 1, message_id: 'm1' },
				turn
			) as { turn: LiveTurn }
		).turn;
		expect(kinds(turn)).toEqual(['tool_call', 'text']);
		const second = turn.blocks[1];
		if (second.kind === 'text') {
			expect(second.text).toBe('orphan');
		}
	});

	it('streams text → tool_use → more text in correct order', () => {
		// End-to-end streaming sequence: open text, deltas, tool call, open new
		// text block, more deltas. Block list must reflect the original order.
		const msgs: WsMessage[] = [
			{ type: 'text_block_start', block_index: 0, message_id: 'm1' },
			{ type: 'text_delta', text: 'Let me ', block_index: 0, message_id: 'm1' },
			{ type: 'text_delta', text: 'check', block_index: 0, message_id: 'm1' },
			{ type: 'tool_use', id: 't1', name: 'Read', message_id: 'm1' },
			{ type: 'tool_input', tool_use_id: 't1', input: { path: '/x' } },
			{ type: 'tool_result', tool_use_id: 't1', content: 'ok', is_error: false },
			{ type: 'text_block_start', block_index: 2, message_id: 'm1' },
			{ type: 'text_delta', text: 'all done', block_index: 2, message_id: 'm1' }
		];
		let turn: LiveTurn | null = emptyTurn();
		for (const m of msgs) {
			turn = (processWsMessage(m, turn) as { turn: LiveTurn }).turn;
		}
		expect(kinds(turn)).toEqual(['text', 'tool_call', 'text']);
		const first = turn.blocks[0];
		const last = turn.blocks[2];
		if (first.kind === 'text') expect(first.text).toBe('Let me check');
		if (last.kind === 'text') expect(last.text).toBe('all done');
	});

	it('grows a thinking block with thinking_delta', () => {
		let turn: LiveTurn | null = emptyTurn();
		turn = (
			processWsMessage(
				{ type: 'thinking_block_start', block_index: 0, message_id: 'm1' },
				turn
			) as { turn: LiveTurn }
		).turn;
		for (const chunk of ['Let ', 'me ', 'reason']) {
			turn = (
				processWsMessage(
					{ type: 'thinking_delta', thinking: chunk, block_index: 0, message_id: 'm1' },
					turn
				) as { turn: LiveTurn }
			).turn;
		}
		expect(kinds(turn)).toEqual(['thinking']);
		const block = turn.blocks[0];
		if (block.kind === 'thinking') {
			expect(block.thinking).toBe('Let me reason');
		}
	});

	it('returns finalize on result', () => {
		const turn = emptyTurn();
		turn.blocks = [{ kind: 'text', text: 'done', revealed: 4 }];

		const msg: WsMessage = {
			type: 'result',
			session_id: 's1',
			duration_ms: 100,
			total_cost_usd: 0.01,
			num_turns: 1,
			is_error: false,
			created_files: []
		};
		const action = processWsMessage(msg, turn);

		expect(action.kind).toBe('finalize');
		if (action.kind === 'finalize') {
			expect(action.turn.blocks).toHaveLength(1);
		}
	});

	it('returns error on error message', () => {
		const msg: WsMessage = { type: 'error', message: 'something broke' };
		const action = processWsMessage(msg, emptyTurn());
		expect(action.kind).toBe('error');
	});

	it('does not mutate input turn', () => {
		const turn = emptyTurn();
		const original = JSON.stringify(turn);

		const msg: WsMessage = { type: 'thinking', thinking: 'new', message_id: 'm1' };
		processWsMessage(msg, turn);

		expect(JSON.stringify(turn)).toBe(original);
	});
});
