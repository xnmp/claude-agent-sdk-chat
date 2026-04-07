import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/svelte';
import ThinkingBlock from '../src/components/ThinkingBlock.svelte';
import type { ThinkingEntry } from '$lib/types';

describe('ThinkingBlock', () => {
	afterEach(cleanup);

	it('renders nothing when entries is empty', () => {
		const { container } = render(ThinkingBlock, { props: { entries: [] } });
		expect(container.querySelector('.thinking')).toBeNull();
	});

	it('renders thinking content', () => {
		const entries: ThinkingEntry[] = [
			{ thinking: 'Let me analyze this...', signature: 'sig1' }
		];
		render(ThinkingBlock, { props: { entries } });
		expect(screen.getByText('Let me analyze this...')).toBeInTheDocument();
	});

	it('renders multiple thinking entries', () => {
		const entries: ThinkingEntry[] = [
			{ thinking: 'Step 1: read file', signature: 's1' },
			{ thinking: 'Step 2: analyze', signature: 's2' }
		];
		render(ThinkingBlock, { props: { entries } });
		expect(screen.getByText('Step 1: read file')).toBeInTheDocument();
		expect(screen.getByText('Step 2: analyze')).toBeInTheDocument();
	});

	it('shows Thinking summary label', () => {
		const entries: ThinkingEntry[] = [{ thinking: 'hmm', signature: 's' }];
		render(ThinkingBlock, { props: { entries } });
		expect(screen.getByText('Thinking')).toBeInTheDocument();
	});
});
