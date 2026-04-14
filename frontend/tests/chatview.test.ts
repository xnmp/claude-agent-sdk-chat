import { describe, it, expect, afterEach, beforeEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import ChatView from '../src/components/ChatView.svelte';
import type { Message, LiveTurn } from '$lib/types';

/**
 * Regression tests for the auto-follow scroll fix.
 *
 * The bugs being guarded against:
 *
 * 1. **Container shrink not observed.** When a turn finishes and
 *    MessageInput's suggestions section appears, the input area grows
 *    and `.messages` shrinks (clientHeight changes). The original
 *    ResizeObserver only watched `messagesInner`, whose box didn't
 *    change, so the auto-follow left the user ~84px above the bottom.
 *    Fix: also observe the scrollContainer.
 *
 * 2. **Smooth scroll racing stale targets.** The original effect used
 *    `behavior: 'smooth'` and only fired on `messages.length` /
 *    `liveTurn?.blocks.length`. Text/tool deltas growing blocks in
 *    place didn't trigger it, and smooth animations captured stale
 *    scroll targets. Fix: ResizeObserver + direct scrollTop assignment.
 *
 * 3. **Wheel-up disengage.** Users reading a long essay mid-stream
 *    should not be yanked back when more content arrives. Wheel
 *    events with deltaY < 0 disengage stickiness; scrolling back to
 *    within REENGAGE_PX of the bottom re-engages.
 */

interface ResizeObserverState {
	instances: MockResizeObserver[];
}

class MockResizeObserver {
	callback: ResizeObserverCallback;
	observed: Element[] = [];

	constructor(cb: ResizeObserverCallback) {
		this.callback = cb;
		state.instances.push(this);
	}

	observe(el: Element) {
		this.observed.push(el);
	}

	unobserve(el: Element) {
		this.observed = this.observed.filter((e) => e !== el);
	}

	disconnect() {
		this.observed = [];
	}

	/** Test helper — fire the callback as if a watched element resized. */
	trigger() {
		this.callback([] as unknown as ResizeObserverEntry[], this as unknown as ResizeObserver);
	}
}

let state: ResizeObserverState;

beforeEach(() => {
	state = { instances: [] };
	(globalThis as unknown as { ResizeObserver: typeof MockResizeObserver }).ResizeObserver =
		MockResizeObserver;
});

afterEach(() => {
	cleanup();
});

function defaultProps() {
	return {
		messages: [] as Message[],
		liveTurn: null as LiveTurn | null,
		isStreaming: false,
		wsStatus: 'connected' as const,
		settings: { theme: 'light' as const, showCost: false, showDuration: false },
		conversationId: 'conv-1',
		onSend: () => {},
		onInterrupt: () => {}
	};
}

describe('ChatView auto-follow', () => {
	it('observes BOTH the inner content and the scroll container', () => {
		// Regression: original code only observed messagesInner. When the
		// suggestions section caused the messages container to shrink, no
		// observer fired and the user was stranded ~84px above the bottom.
		const { container } = render(ChatView, { props: defaultProps() });

		expect(state.instances).toHaveLength(1);
		const ro = state.instances[0];

		const scrollContainer = container.querySelector('.messages');
		const messagesInner = container.querySelector('.messages-inner');
		expect(scrollContainer).toBeTruthy();
		expect(messagesInner).toBeTruthy();

		expect(ro.observed).toContain(scrollContainer);
		expect(ro.observed).toContain(messagesInner);
		expect(ro.observed).toHaveLength(2);
	});

	it('scrolls to the bottom when the observer fires while sticky', () => {
		const { container } = render(ChatView, { props: defaultProps() });
		const scrollContainer = container.querySelector('.messages') as HTMLElement;

		// jsdom doesn't compute layout, so fake a scroll geometry.
		Object.defineProperty(scrollContainer, 'scrollHeight', { configurable: true, value: 5000 });
		Object.defineProperty(scrollContainer, 'clientHeight', { configurable: true, value: 300 });
		scrollContainer.scrollTop = 0;

		state.instances[0].trigger();

		// The follow callback assigns scrollTop = scrollHeight; jsdom clamps
		// the assignment to (scrollHeight - clientHeight) or accepts the raw
		// value depending on the version. Either way it must end up at the
		// bottom (or beyond, before clamp).
		expect(scrollContainer.scrollTop).toBeGreaterThanOrEqual(4700);
	});

	it('does NOT scroll when sticky is disengaged via wheel-up', async () => {
		// Regression: text deltas growing blocks in place would yank the
		// user back to the bottom even after they scrolled up to read.
		const { container } = render(ChatView, { props: defaultProps() });
		const scrollContainer = container.querySelector('.messages') as HTMLElement;

		Object.defineProperty(scrollContainer, 'scrollHeight', { configurable: true, value: 5000 });
		Object.defineProperty(scrollContainer, 'clientHeight', { configurable: true, value: 300 });
		scrollContainer.scrollTop = 1000;

		// Disengage by simulating a wheel-up.
		await fireEvent.wheel(scrollContainer, { deltaY: -100 });

		const before = scrollContainer.scrollTop;
		state.instances[0].trigger();

		// Position must be unchanged — the user is reading above and we
		// should NOT have followed the bottom.
		expect(scrollContainer.scrollTop).toBe(before);
	});

	it('downward wheel does not disengage', async () => {
		// Sanity check: only deltaY < 0 should affect stickiness.
		const { container } = render(ChatView, { props: defaultProps() });
		const scrollContainer = container.querySelector('.messages') as HTMLElement;

		Object.defineProperty(scrollContainer, 'scrollHeight', { configurable: true, value: 5000 });
		Object.defineProperty(scrollContainer, 'clientHeight', { configurable: true, value: 300 });
		scrollContainer.scrollTop = 0;

		await fireEvent.wheel(scrollContainer, { deltaY: 100 });
		state.instances[0].trigger();

		// Sticky was never disengaged, so the trigger should still scroll
		// to the bottom.
		expect(scrollContainer.scrollTop).toBeGreaterThanOrEqual(4700);
	});

	it('re-engages when the user scrolls back to the bottom', async () => {
		// After wheel-up disengages, scrolling back to within REENGAGE_PX
		// of the bottom should restore auto-follow.
		const { container } = render(ChatView, { props: defaultProps() });
		const scrollContainer = container.querySelector('.messages') as HTMLElement;

		Object.defineProperty(scrollContainer, 'scrollHeight', { configurable: true, value: 5000 });
		Object.defineProperty(scrollContainer, 'clientHeight', { configurable: true, value: 300 });
		scrollContainer.scrollTop = 1000;

		// Disengage
		await fireEvent.wheel(scrollContainer, { deltaY: -100 });

		// Now scroll back to the bottom — handleScroll should set sticky=true
		scrollContainer.scrollTop = 4700; // exactly at maxScroll
		await fireEvent.scroll(scrollContainer);

		// Move scrollTop somewhere else, then trigger the observer. If sticky
		// re-engaged, the observer should yank us back to the bottom.
		scrollContainer.scrollTop = 2000;
		state.instances[0].trigger();

		expect(scrollContainer.scrollTop).toBeGreaterThanOrEqual(4700);
	});
});
