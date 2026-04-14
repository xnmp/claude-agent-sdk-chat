import { describe, it, expect, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import StreamingMarkdown from '../src/components/StreamingMarkdown.svelte';

describe('StreamingMarkdown', () => {
	afterEach(cleanup);

	it('renders the substring up to revealed', () => {
		// The component is a dumb view over a typewriter cursor — it renders
		// text.slice(0, revealed). The ticker in +page.svelte owns the advance;
		// here we just check that the slice is honored.
		const { container } = render(StreamingMarkdown, {
			props: { text: 'Hello, world!', revealed: 5 }
		});
		expect(container.textContent).toContain('Hello');
		expect(container.textContent).not.toContain('world');
	});

	it('renders an empty container when revealed is 0', () => {
		const { container } = render(StreamingMarkdown, {
			props: { text: 'anything at all', revealed: 0 }
		});
		expect(container.textContent?.trim() ?? '').toBe('');
	});

	it('renders the full text when revealed equals text.length', () => {
		const { container } = render(StreamingMarkdown, {
			props: { text: 'The quick brown fox', revealed: 19 }
		});
		expect(container.textContent).toContain('The quick brown fox');
	});

	it('parses markdown formatting in the visible slice', () => {
		const { container } = render(StreamingMarkdown, {
			props: { text: '**bold** and *italic*', revealed: 21 }
		});
		expect(container.querySelector('strong')?.textContent).toBe('bold');
		expect(container.querySelector('em')?.textContent).toBe('italic');
	});
});
