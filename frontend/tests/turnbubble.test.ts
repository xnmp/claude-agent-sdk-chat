import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import TurnBubble from '../src/components/TurnBubble.svelte';
import type { Message, AssistantContent, LiveTurn } from '$lib/types';

function userMessage(text: string): Message {
	return {
		id: crypto.randomUUID(),
		conversation_id: 'conv-1',
		role: 'user',
		content: { text },
		created_at: new Date().toISOString()
	};
}

function assistantMessage(overrides: Partial<AssistantContent> = {}): Message {
	return {
		id: crypto.randomUUID(),
		conversation_id: 'conv-1',
		role: 'assistant',
		content: {
			thinking: [],
			tool_calls: [],
			text: 'Response text',
			model: 'claude-sonnet-4-20250514',
			usage: {},
			duration_ms: 1500,
			total_cost_usd: 0.003,
			created_files: [],
			...overrides
		},
		created_at: new Date().toISOString()
	};
}

describe('TurnBubble', () => {
	afterEach(cleanup);

	it('renders user message text', () => {
		render(TurnBubble, { props: { message: userMessage('Hello world') } });
		expect(screen.getByText('Hello world')).toBeInTheDocument();
	});

	it('renders user message with user bubble styling', () => {
		const { container } = render(TurnBubble, { props: { message: userMessage('hi') } });
		expect(container.querySelector('.user-bubble')).toBeTruthy();
	});

	it('renders assistant response text', () => {
		render(TurnBubble, { props: { message: assistantMessage({ text: 'The answer is 42' }) } });
		expect(screen.getByText('The answer is 42')).toBeInTheDocument();
	});

	it('renders cost and duration metadata', () => {
		render(TurnBubble, {
			props: { message: assistantMessage({ total_cost_usd: 0.0123, duration_ms: 3500 }) }
		});
		expect(screen.getByText('$0.0123')).toBeInTheDocument();
		expect(screen.getByText('3.5s')).toBeInTheDocument();
	});

	it('hides metadata when cost is zero', () => {
		const { container } = render(TurnBubble, {
			props: { message: assistantMessage({ total_cost_usd: 0, duration_ms: 0 }) }
		});
		expect(container.querySelector('.meta')).toBeNull();
	});

	it('shows tool call toggle when tool calls present', () => {
		render(TurnBubble, {
			props: {
				message: assistantMessage({
					tool_calls: [
						{ id: 't1', name: 'Read', input: {}, result: 'ok', is_error: false }
					]
				})
			}
		});
		expect(screen.getByText(/1 tool call$/)).toBeInTheDocument();
	});

	it('pluralizes tool call count correctly', () => {
		render(TurnBubble, {
			props: {
				message: assistantMessage({
					tool_calls: [
						{ id: 't1', name: 'Read', input: {}, result: 'ok', is_error: false },
						{ id: 't2', name: 'Grep', input: {}, result: 'ok', is_error: false }
					]
				})
			}
		});
		expect(screen.getByText(/2 tool calls$/)).toBeInTheDocument();
	});

	it('shows streaming indicator for live turn without text', () => {
		const liveTurn: LiveTurn = { startedAt: Date.now(), thinking: [], tool_calls: [], text: '' };
		const { container } = render(TurnBubble, {
			props: { liveTurn, isLive: true }
		});
		expect(container.querySelectorAll('.dot')).toHaveLength(3);
	});

	it('shows text for live turn with text', () => {
		const liveTurn: LiveTurn = { startedAt: Date.now(), thinking: [], tool_calls: [], text: 'Streaming...' };
		render(TurnBubble, { props: { liveTurn, isLive: true } });
		expect(screen.getByText('Streaming...')).toBeInTheDocument();
	});

	it('expands tool calls on toggle click', async () => {
		const user = userEvent.setup();
		render(TurnBubble, {
			props: {
				message: assistantMessage({
					tool_calls: [
						{ id: 't1', name: 'Read', input: { file_path: '/tmp/x' }, result: 'contents', is_error: false }
					]
				})
			}
		});

		await user.click(screen.getByText(/1 tool call$/));
		// After expanding, the tool name should be visible inside sub-messages
		expect(screen.getByText('Read')).toBeInTheDocument();
	});

	it('renders download links for created files', () => {
		render(TurnBubble, {
			props: {
				message: assistantMessage({
					created_files: ['report.csv', 'chart.png']
				})
			}
		});
		const links = screen.getAllByRole('link');
		expect(links).toHaveLength(2);
		expect(links[0]).toHaveTextContent('report.csv');
		expect(links[1]).toHaveTextContent('chart.png');
		expect(links[0]).toHaveAttribute('href', expect.stringContaining('report.csv'));
	});

	it('does not render download section when no created files', () => {
		const { container } = render(TurnBubble, {
			props: { message: assistantMessage({ created_files: [] }) }
		});
		expect(container.querySelector('.created-files')).toBeNull();
	});
});
