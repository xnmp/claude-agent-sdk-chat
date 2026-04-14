/**
 * Typewriter ticker — advances each text block's `revealed` cursor toward
 * `text.length` so the model's output appears progressively even when the
 * SDK delivers it in bursty chunks.
 *
 * Strategy: the rate is held *constant* between deltas, recalculated only
 * when a new delta arrives. On each delta the typewriter looks at the
 * current backlog (`text.length - revealed`) and picks a rate that would
 * drain it in `TARGET_DRAIN_MS` (~1 second). Until the next delta arrives
 * the typewriter coasts at that rate.
 *
 * This avoids the exponential-decay tail you'd get with a backlog-proportional
 * rate recomputed every frame: the rate doesn't fall as the backlog shrinks,
 * so the cursor genuinely lands on `text.length` after one drain interval
 * instead of asymptoting to it.
 *
 * Per-block state (last-seen text length, fractional accumulator, current
 * rate) lives in a `WeakMap` keyed on the block reference, so when a block
 * is garbage-collected its state goes with it and nothing about the
 * typewriter leaks into the persisted block shape.
 */

import type { Block } from './types';

/** Target drain time in milliseconds for any newly-arrived backlog. */
export const TYPEWRITER_TARGET_DRAIN_MS = 1000;

/**
 * Floor speed in chars/ms when the backlog is small. ~25 chars/sec keeps
 * single-character streams looking like a typewriter rather than dumping
 * each char instantly.
 */
export const TYPEWRITER_BASE_RATE = 0.025;

interface BlockState {
	/** Fractional chars accumulated across frames at sub-frame rates. */
	accumulator: number;
	/** Constant rate (chars/ms) until the next delta updates it. */
	rate: number;
	/** Last `text.length` we observed; if it changes, recalculate `rate`. */
	lastTextLength: number;
}

export interface TypewriterTicker {
	/**
	 * Advance every text block in `blocks` by one frame's worth of progress.
	 * Returns true while any block still has work, so the caller can decide
	 * whether to schedule another animation frame.
	 */
	advanceBlocks(blocks: Block[], dt: number): boolean;
	/** Drop tracked state for `block` — used when explicitly discarding it. */
	forget(block: object): void;
}

export function createTypewriter(): TypewriterTicker {
	const state = new WeakMap<object, BlockState>();

	function advanceBlocks(blocks: Block[], dt: number): boolean {
		let stillTyping = false;
		for (const block of blocks) {
			if (block.kind !== 'text') continue;
			const remaining = block.text.length - block.revealed;
			if (remaining <= 0) {
				state.delete(block);
				continue;
			}

			let s = state.get(block);
			if (!s) {
				s = { accumulator: 0, rate: 0, lastTextLength: -1 };
				state.set(block, s);
			}

			// New delta arrived (or first frame for this block) — recompute the
			// rate so the *current* remaining backlog drains in TARGET_DRAIN_MS.
			if (block.text.length !== s.lastTextLength) {
				s.lastTextLength = block.text.length;
				s.rate = Math.max(TYPEWRITER_BASE_RATE, remaining / TYPEWRITER_TARGET_DRAIN_MS);
			}

			// Advance using the held rate. Sub-frame fractions accumulate so
			// rates below 1 char/frame still progress on every Nth frame.
			s.accumulator += s.rate * dt;
			const advance = Math.floor(s.accumulator);
			s.accumulator -= advance;

			if (advance > 0) {
				block.revealed = Math.min(block.text.length, block.revealed + advance);
			}
			stillTyping = true;
		}
		return stillTyping;
	}

	function forget(block: object) {
		state.delete(block);
	}

	return { advanceBlocks, forget };
}
