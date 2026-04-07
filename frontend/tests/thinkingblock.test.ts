import { describe, it, expect, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import ThinkingBlock from '../src/components/ThinkingBlock.svelte';

describe('ThinkingBlock', () => {
	afterEach(cleanup);

	it('renders nothing when entries is empty', () => {
		const { container } = render(ThinkingBlock, { props: { entries: [] } });
		expect(container.querySelector('.thinking')).toBeNull();
	});
});
