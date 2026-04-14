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
			blocks: [{ kind: 'text', text: 'Response text', revealed: 'Response text'.length }],
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
					blocks: [{ kind: 'text', text: 'The answer is 42', revealed: 16 }]
				})
			}
		});
		expect(screen.getByText('The answer is 42')).toBeInTheDocument();
	});

	it('renders interleaved text blocks in order', () => {
		// Regression: a turn with text → tool → text used to drop the first text.
		const blocks: Block[] = [
			{ kind: 'text', text: 'let me check', revealed: 12 },
			{
				kind: 'tool_call',
				id: 't1',
				name: 'Read',
				input: { file_path: '/tmp/x' },
				result: 'contents',
				is_error: false
			},
			{ kind: 'text', text: 'all set', revealed: 7 }
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
						{ kind: 'text', text: 'reading the file', revealed: 16 },
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

	it('shows text for live turn with a fully-revealed text block', () => {
		// The typewriter cursor (revealed) is owned by +page.svelte's ticker,
		// not TurnBubble. In a unit test we just pass the block with its
		// desired visible cursor already set.
		const liveTurn: LiveTurn = {
			startedAt: Date.now(),
			blocks: [{ kind: 'text', text: 'Streaming...', revealed: 'Streaming...'.length }]
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

	it('strips session_id prefix from the link label but keeps it in the href', () => {
		// Post per-session-output-folders, created_files come in as
		// "<session_id>/<name>" so the /api/output static mount resolves them.
		// The displayed label should be just the filename.
		const sessionId = 'b236f25b-d2c4-47a1-b617-08be5d5074a6';
		render(TurnBubble, {
			props: {
				message: assistantMessage({
					created_files: [`${sessionId}/hello.md`]
				})
			}
		});
		const link = screen.getByRole('link');
		expect(link).toHaveTextContent('hello.md');
		expect(link).not.toHaveTextContent(sessionId);
		expect(link).toHaveAttribute(
			'href',
			expect.stringContaining(`${sessionId}/hello.md`)
		);
		expect(link).toHaveAttribute('download', 'hello.md');
	});

	it('preserves non-UUID first segments in the link label', () => {
		// Legitimate nested output (e.g. from older turns before the session
		// scoping) should not be mangled by the UUID-prefix stripper.
		render(TurnBubble, {
			props: {
				message: assistantMessage({
					created_files: ['analysis/results.csv']
				})
			}
		});
		const link = screen.getByRole('link');
		expect(link).toHaveTextContent('analysis/results.csv');
	});

	it('renders TodoWrite tool calls as a todo list widget', () => {
		const blocks: Block[] = [
			{
				kind: 'tool_call',
				id: 'tw1',
				name: 'TodoWrite',
				input: {
					todos: [
						{ content: 'Design', status: 'completed', activeForm: 'Designing' },
						{ content: 'Build API', status: 'in_progress', activeForm: 'Building API' },
						{ content: 'Write tests', status: 'pending', activeForm: 'Writing tests' }
					]
				},
				result: 'ok',
				is_error: false
			}
		];
		const { container } = render(TurnBubble, {
			props: { message: assistantMessage({ blocks }) }
		});

		// The generic ToolCall component must NOT be used for TodoWrite.
		expect(container.querySelector('.tool-call')).toBeNull();

		// Instead, a dedicated todo-list widget is rendered.
		expect(container.querySelector('.todo-list')).not.toBeNull();
		expect(screen.getByText('1/3')).toBeInTheDocument();

		// Completed item shows the base content, in_progress item shows the activeForm.
		expect(screen.getByText('Design')).toBeInTheDocument();
		expect(screen.getByText('Building API')).toBeInTheDocument();
		expect(screen.getByText('Write tests')).toBeInTheDocument();
	});

	it('merges multiple TodoWrite calls into a single widget showing latest state', () => {
		// The agent calls TodoWrite repeatedly to update statuses. We want the
		// widget to "fill in place" — the list appears once at the first
		// TodoWrite position and reflects the LATEST snapshot, not a separate
		// widget per call.
		const blocks: Block[] = [
			{
				kind: 'tool_call',
				id: 'tw1',
				name: 'TodoWrite',
				input: {
					todos: [
						{ content: 'Step one', status: 'pending', activeForm: 'Doing step one' },
						{ content: 'Step two', status: 'pending', activeForm: 'Doing step two' }
					]
				},
				result: 'ok',
				is_error: false
			},
			{
				kind: 'tool_call',
				id: 'b1',
				name: 'Bash',
				input: { command: 'ls' },
				result: 'file.txt',
				is_error: false
			},
			{
				kind: 'tool_call',
				id: 'tw2',
				name: 'TodoWrite',
				input: {
					todos: [
						{ content: 'Step one', status: 'completed', activeForm: 'Doing step one' },
						{ content: 'Step two', status: 'in_progress', activeForm: 'Doing step two' }
					]
				},
				result: 'ok',
				is_error: false
			}
		];
		const { container } = render(TurnBubble, {
			props: { message: assistantMessage({ blocks }) }
		});

		// Exactly one TodoList widget, showing the latest counts (1 of 2 done).
		expect(container.querySelectorAll('.todo-list')).toHaveLength(1);
		expect(screen.getByText('1/2')).toBeInTheDocument();

		// The unrelated Bash tool call still renders as a normal ToolCall.
		expect(container.querySelectorAll('.tool-call')).toHaveLength(1);
		expect(screen.getByText('Bash')).toBeInTheDocument();

		// In-progress item is labeled with its activeForm.
		expect(screen.getByText('Doing step two')).toBeInTheDocument();
	});

	it('does not render download section when no created files', () => {
		const { container } = render(TurnBubble, {
			props: { message: assistantMessage({ created_files: [] }) }
		});
		expect(container.querySelector('.created-files')).toBeNull();
	});
});
