import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/svelte';
import ToolCall from '../src/components/ToolCall.svelte';
import type { ToolCallEntry } from '$lib/types';

function makeTool(overrides: Partial<ToolCallEntry> = {}): ToolCallEntry {
	return {
		id: 't1',
		name: 'Read',
		input: {},
		result: null,
		is_error: null,
		...overrides
	};
}

describe('ToolCall', () => {
	afterEach(cleanup);

	it('shows tool name', () => {
		render(ToolCall, { props: { tool: makeTool({ name: 'Grep' }) } });
		expect(screen.getByText('Grep')).toBeInTheDocument();
	});

	it('shows running status when result is null', () => {
		render(ToolCall, { props: { tool: makeTool({ result: null }) } });
		expect(screen.getByText('running...')).toBeInTheDocument();
	});

	it('shows done status on success', () => {
		render(ToolCall, { props: { tool: makeTool({ result: 'output', is_error: false }) } });
		expect(screen.getByText('done')).toBeInTheDocument();
	});

	it('shows error status on failure', () => {
		render(ToolCall, { props: { tool: makeTool({ result: 'failed', is_error: true }) } });
		expect(screen.getByText('error')).toBeInTheDocument();
	});

	it('applies correct status CSS class', () => {
		const { container } = render(ToolCall, {
			props: { tool: makeTool({ result: 'ok', is_error: false }) }
		});
		expect(container.querySelector('.status.success')).toBeTruthy();
	});

	it('applies error CSS class for errors', () => {
		const { container } = render(ToolCall, {
			props: { tool: makeTool({ result: 'err', is_error: true }) }
		});
		expect(container.querySelector('.status.error')).toBeTruthy();
	});
});
