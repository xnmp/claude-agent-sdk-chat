import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import TurnBubble from '../src/components/TurnBubble.svelte';
import type { Block, Message, AssistantContent, LiveTurn } from '$lib/types';

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
			blocks: [{ kind: 'text', text: 'Response text' }],
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

	it('renders assistant text block', () => {
		render(TurnBubble, {
			props: {
				message: assistantMessage({
					blocks: [{ kind: 'text', text: 'The answer is 42' }]
				})
			}
		});
		expect(screen.getByText('The answer is 42')).toBeInTheDocument();
	});

	it('renders interleaved text blocks in order', () => {
		// Regression: a turn with text → tool → text used to drop the first text.
		const blocks: Block[] = [
			{ kind: 'text', text: 'let me check' },
			{
				kind: 'tool_call',
				id: 't1',
				name: 'Read',
				input: { file_path: '/tmp/x' },
				result: 'contents',
				is_error: false
			},
			{ kind: 'text', text: 'all set' }
		];
		const { container } = render(TurnBubble, {
			props: { message: assistantMessage({ blocks }) }
		});

		// Both text blocks survive (regression: previously only the last did).
		const textBlocks = container.querySelectorAll('.response-text');
		expect(textBlocks).toHaveLength(2);
		expect(textBlocks[0].textContent).toContain('let me check');
		expect(textBlocks[1].textContent).toContain('all set');

		// Order: text → tool → text. Index of the tool call must lie between
		// the two text blocks in the DOM.
		const toolCall = container.querySelector('.tool-call');
		expect(toolCall).not.toBeNull();
		const all = Array.from(container.querySelectorAll('.response-text, .tool-call'));
		expect(all.map((el) => el.classList.contains('tool-call'))).toEqual([
			false,
			true,
			false
		]);
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

	it('renders inline tool call alongside text', () => {
		render(TurnBubble, {
			props: {
				message: assistantMessage({
					blocks: [
						{ kind: 'text', text: 'reading the file' },
						{
							kind: 'tool_call',
							id: 't1',
							name: 'Read',
							input: {},
							result: 'ok',
							is_error: false
						}
					]
				})
			}
		});
		expect(screen.getByText('reading the file')).toBeInTheDocument();
		expect(screen.getByText('Read')).toBeInTheDocument();
	});

	it('shows streaming dots for live turn with no blocks', () => {
		const liveTurn: LiveTurn = { startedAt: Date.now(), blocks: [] };
		const { container } = render(TurnBubble, {
			props: { liveTurn, isLive: true }
		});
		expect(container.querySelectorAll('.dot')).toHaveLength(3);
	});

	it('shows text for live turn with text block', () => {
		const liveTurn: LiveTurn = {
			startedAt: Date.now(),
			blocks: [{ kind: 'text', text: 'Streaming...' }]
		};
		render(TurnBubble, { props: { liveTurn, isLive: true } });
		expect(screen.getByText('Streaming...')).toBeInTheDocument();
	});

	it('expands tool call details on click', async () => {
		const user = userEvent.setup();
		render(TurnBubble, {
			props: {
				message: assistantMessage({
					blocks: [
						{
							kind: 'tool_call',
							id: 't1',
							name: 'Read',
							input: { file_path: '/tmp/x' },
							result: 'contents',
							is_error: false
						}
					]
				})
			}
		});

		// Click the <details> summary to expand
		await user.click(screen.getByText('Read'));
		// Once expanded the input/output sections appear
		expect(screen.getByText('Input')).toBeInTheDocument();
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
