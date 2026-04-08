import { describe, it, expect } from 'vitest';
import { processWsMessage } from '$lib/liveTurnReducer';
import type { LiveTurn, WsMessage } from '$lib/types';

function emptyTurn(): LiveTurn {
	return { thinking: [], tool_calls: [], text: '' };
}

describe('processWsMessage', () => {
	it('creates turn from null on thinking message', () => {
		const msg: WsMessage = { type: 'thinking', thinking: 'hmm', message_id: 'm1' };
		const action = processWsMessage(msg, null);

		expect(action.kind).toBe('update');
		if (action.kind === 'update') {
			expect(action.turn.thinking).toHaveLength(1);
			expect(action.turn.thinking[0].thinking).toBe('hmm');
		}
	});

	it('appends thinking to existing turn', () => {
		const turn = emptyTurn();
		turn.thinking = [{ thinking: 'first', signature: '' }];

		const msg: WsMessage = { type: 'thinking', thinking: 'second', message_id: 'm1' };
		const action = processWsMessage(msg, turn);

		if (action.kind === 'update') {
			expect(action.turn.thinking).toHaveLength(2);
			expect(action.turn.thinking[1].thinking).toBe('second');
		}
	});

	it('adds tool_use to turn', () => {
		const msg: WsMessage = { type: 'tool_use', id: 't1', name: 'Read', message_id: 'm1' };
		const action = processWsMessage(msg, emptyTurn());

		if (action.kind === 'update') {
			expect(action.turn.tool_calls).toHaveLength(1);
			expect(action.turn.tool_calls[0]).toMatchObject({ id: 't1', name: 'Read' });
		}
	});

	it('updates tool_call input on tool_input', () => {
		const turn = emptyTurn();
		turn.tool_calls = [{ id: 't1', name: 'Read', input: {}, result: null, is_error: null }];

		const msg: WsMessage = { type: 'tool_input', tool_use_id: 't1', input: { path: '/tmp' } };
		const action = processWsMessage(msg, turn);

		if (action.kind === 'update') {
			expect(action.turn.tool_calls[0].input).toEqual({ path: '/tmp' });
		}
	});

	it('updates tool_call result on tool_result', () => {
		const turn = emptyTurn();
		turn.tool_calls = [{ id: 't1', name: 'Read', input: {}, result: null, is_error: null }];

		const msg: WsMessage = {
			type: 'tool_result',
			tool_use_id: 't1',
			content: 'file contents',
			is_error: false
		};
		const action = processWsMessage(msg, turn);

		if (action.kind === 'update') {
			expect(action.turn.tool_calls[0].result).toBe('file contents');
			expect(action.turn.tool_calls[0].is_error).toBe(false);
		}
	});

	it('sets text on assistant_text', () => {
		const msg: WsMessage = { type: 'assistant_text', text: 'Hello!', message_id: 'm1' };
		const action = processWsMessage(msg, emptyTurn());

		if (action.kind === 'update') {
			expect(action.turn.text).toBe('Hello!');
		}
	});

	it('overwrites text on subsequent assistant_text', () => {
		const turn = emptyTurn();
		turn.text = 'partial';

		const msg: WsMessage = { type: 'assistant_text', text: 'partial response', message_id: 'm1' };
		const action = processWsMessage(msg, turn);

		if (action.kind === 'update') {
			expect(action.turn.text).toBe('partial response');
		}
	});

	it('returns finalize on result', () => {
		const turn = emptyTurn();
		turn.text = 'done';

		const msg: WsMessage = {
			type: 'result',
			session_id: 's1',
			duration_ms: 100,
			total_cost_usd: 0.01,
			num_turns: 1,
			is_error: false
		};
		const action = processWsMessage(msg, turn);

		expect(action.kind).toBe('finalize');
		if (action.kind === 'finalize') {
			expect(action.turn.text).toBe('done');
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
