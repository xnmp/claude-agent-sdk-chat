import { describe, it, expect } from 'vitest';
import { createTypewriter, TYPEWRITER_TARGET_DRAIN_MS } from '$lib/typewriter';
import type { Block, TextBlock } from '$lib/types';

function textBlock(text: string, revealed = 0): TextBlock {
	return { kind: 'text', text, revealed };
}

function drainAt60Fps(tw: ReturnType<typeof createTypewriter>, blocks: Block[], ms: number) {
	const dt = 16; // 60 fps
	for (let elapsed = 0; elapsed < ms; elapsed += dt) {
		tw.advanceBlocks(blocks, dt);
	}
}

describe('typewriter', () => {
	it('advances the revealed cursor toward text.length', () => {
		const tw = createTypewriter();
		const blocks = [textBlock('Hello world')];
		drainAt60Fps(tw, blocks, 600); // > 1s — well past drain target
		expect((blocks[0] as TextBlock).revealed).toBe(11);
	});

	it('advances at sub-frame rates (no per-frame ≥1 floor)', () => {
		// Regression: the old ticker used `Math.max(1, ceil(rate * dt))` which
		// forced ≥1 char per frame at 60 fps — a hard floor of 60 chars/sec
		// regardless of how slow BASE was set. With the accumulator, the BASE
		// rate (25 chars/sec ≈ 0.4 chars/frame) should advance roughly every
		// 2-3 frames, not every frame.
		//
		// Use a 1-char block so the per-block rate is BASE rather than the
		// (much higher) backlog-proportional rate.
		const tw = createTypewriter();
		const blocks = [textBlock('A')];

		// First frame at 16 ms. BASE 0.025 chars/ms × 16 ms = 0.4 chars in
		// the accumulator, still under 1 — must NOT advance yet.
		tw.advanceBlocks(blocks, 16);
		expect((blocks[0] as TextBlock).revealed).toBe(0);

		// Second frame: accumulator now 0.8, still under 1.
		tw.advanceBlocks(blocks, 16);
		expect((blocks[0] as TextBlock).revealed).toBe(0);

		// Third frame: accumulator hits 1.2, advance one char.
		tw.advanceBlocks(blocks, 16);
		expect((blocks[0] as TextBlock).revealed).toBe(1);
	});

	it('drains a fresh backlog in approximately TARGET_DRAIN_MS', () => {
		const tw = createTypewriter();
		const blocks = [textBlock('x'.repeat(500))];

		drainAt60Fps(tw, blocks, TYPEWRITER_TARGET_DRAIN_MS);
		// After ~1s of frames the cursor should have reached the end (within
		// rounding noise from the 16 ms frame quantization).
		expect((blocks[0] as TextBlock).revealed).toBe(500);
	});

	it('holds rate constant between deltas (no exponential decay)', () => {
		// A 1000-char block should drain in TARGET_DRAIN_MS even though the
		// remaining backlog shrinks every frame. With the broken
		// "recompute every frame" logic, the rate would fall as the backlog
		// shrank, giving exponential decay (drain time ≈ 7s for 1000 chars).
		const tw = createTypewriter();
		const blocks = [textBlock('y'.repeat(1000))];

		drainAt60Fps(tw, blocks, TYPEWRITER_TARGET_DRAIN_MS + 32);
		expect((blocks[0] as TextBlock).revealed).toBe(1000);
	});

	it('recalculates rate when a delta grows the text', () => {
		// A delta arrives midway through draining. The new backlog (whatever
		// is unrevealed at that moment) should drain in TARGET_DRAIN_MS *from
		// the delta time*.
		const tw = createTypewriter();
		const blocks: Block[] = [textBlock('z'.repeat(200))];

		// Drain for half the target — should land on roughly half-revealed.
		drainAt60Fps(tw, blocks, TYPEWRITER_TARGET_DRAIN_MS / 2);
		const firstRevealed = (blocks[0] as TextBlock).revealed;
		expect(firstRevealed).toBeGreaterThan(80);
		expect(firstRevealed).toBeLessThan(120);

		// New delta: text grows by 800 chars. Backlog is now (200 - firstRevealed) + 800.
		(blocks[0] as TextBlock).text = 'z'.repeat(1000);

		// Drain for one more TARGET_DRAIN_MS — should land at 1000 (full).
		drainAt60Fps(tw, blocks, TYPEWRITER_TARGET_DRAIN_MS + 32);
		expect((blocks[0] as TextBlock).revealed).toBe(1000);
	});

	it('uses the BASE rate floor for tiny streams', () => {
		// With TARGET_DRAIN_MS = 1000 and base = 0.025, a 1-char block has
		// `1 / 1000 = 0.001` chars/ms which is below the base. The base
		// (25 chars/sec) takes over and the single char appears in ~40 ms.
		const tw = createTypewriter();
		const blocks = [textBlock('A')];

		// 40 ms of frames at 16 ms each → ~3 frames. Accumulator: 0.025 × 48
		// = 1.2 → advance 1.
		drainAt60Fps(tw, blocks, 48);
		expect((blocks[0] as TextBlock).revealed).toBe(1);
	});

	it('does not advance past text.length', () => {
		const tw = createTypewriter();
		const blocks = [textBlock('hi', 2)];
		// Already fully revealed — nothing should change.
		const stillTyping = tw.advanceBlocks(blocks, 16);
		expect((blocks[0] as TextBlock).revealed).toBe(2);
		expect(stillTyping).toBe(false);
	});

	it('returns false when all blocks are fully revealed', () => {
		const tw = createTypewriter();
		const blocks = [textBlock('done', 4)];
		expect(tw.advanceBlocks(blocks, 16)).toBe(false);
	});

	it('returns true while any block still has work', () => {
		const tw = createTypewriter();
		const blocks = [textBlock('done', 4), textBlock('not done', 0)];
		expect(tw.advanceBlocks(blocks, 16)).toBe(true);
	});

	it('ignores non-text blocks', () => {
		const tw = createTypewriter();
		const blocks: Block[] = [
			{ kind: 'thinking', thinking: 'pondering', signature: '' },
			{
				kind: 'tool_call',
				id: 't1',
				name: 'Read',
				input: {},
				result: 'ok',
				is_error: false
			}
		];
		// Should be a no-op — the tool call and thinking shouldn't crash or
		// keep the loop alive.
		expect(tw.advanceBlocks(blocks, 16)).toBe(false);
	});
});
