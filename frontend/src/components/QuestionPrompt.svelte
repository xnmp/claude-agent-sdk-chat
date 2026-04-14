<script lang="ts">
	import type { QuestionBlock } from '$lib/types';

	let {
		question,
		onAnswer
	}: {
		question: QuestionBlock;
		onAnswer: (toolUseId: string, answer: string) => void;
	} = $props();

	let showOtherInput = $state(false);
	let otherText = $state('');
	let otherInputEl: HTMLInputElement | undefined = $state();

	// Strip any agent-supplied "other" / "other..." option — the component
	// always renders its own "Other..." escape hatch, so leaving the agent's
	// version in would render two of them.
	function isOtherLabel(label: string): boolean {
		return label.trim().toLowerCase().replace(/[.…]+$/, '') === 'other';
	}
	let displayOptions = $derived(question.options.filter((o) => !isOtherLabel(o)));

	function handleClick(option: string) {
		if (question.answered) return;
		onAnswer(question.tool_use_id, option);
	}

	function openOtherInput() {
		if (question.answered) return;
		showOtherInput = true;
		// Focus once Svelte mounts the input
		queueMicrotask(() => otherInputEl?.focus());
	}

	function cancelOtherInput() {
		showOtherInput = false;
		otherText = '';
	}

	function submitOther() {
		const trimmed = otherText.trim();
		if (!trimmed || question.answered) return;
		onAnswer(question.tool_use_id, trimmed);
		showOtherInput = false;
	}

	function handleOtherKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault();
			submitOther();
		} else if (e.key === 'Escape') {
			e.preventDefault();
			cancelOtherInput();
		}
	}
</script>

<div class="question-prompt" class:answered={question.answered}>
	{#if question.question}
		<div class="prompt-text">{question.question}</div>
	{:else}
		<div class="prompt-text placeholder">…</div>
	{/if}

	{#if displayOptions.length > 0 || !question.answered}
		<div class="options">
			{#each displayOptions as option}
				<button
					type="button"
					class="option"
					class:selected={question.selected === option}
					disabled={question.answered}
					onclick={() => handleClick(option)}
				>
					{option}
				</button>
			{/each}

			{#if !question.answered && !showOtherInput}
				<button
					type="button"
					class="option option-other"
					onclick={openOtherInput}
				>
					Other…
				</button>
			{/if}
		</div>
	{/if}

	{#if showOtherInput && !question.answered}
		<div class="other-input-row">
			<input
				bind:this={otherInputEl}
				bind:value={otherText}
				type="text"
				class="other-input"
				placeholder="Type your answer…"
				onkeydown={handleOtherKeydown}
			/>
			<button
				type="button"
				class="other-submit"
				disabled={!otherText.trim()}
				onclick={submitOther}
			>
				Send
			</button>
			<button type="button" class="other-cancel" onclick={cancelOtherInput}>
				Cancel
			</button>
		</div>
	{/if}

	{#if question.answered && question.selected !== null}
		<div class="answered-note">You chose <strong>{question.selected}</strong></div>
	{/if}
</div>

<style>
	.question-prompt {
		border: 1px solid var(--accent-muted);
		background: var(--accent-subtle);
		border-radius: var(--radius);
		padding: 12px 14px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.question-prompt.answered {
		border-color: var(--border);
		background: var(--bg-inset);
	}

	.prompt-text {
		font-size: 0.9375rem;
		font-weight: 500;
		color: var(--text);
		line-height: 1.4;
	}

	.prompt-text.placeholder {
		color: var(--text-dim);
		font-style: italic;
	}

	.options {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}

	.option {
		appearance: none;
		font: inherit;
		font-size: 0.875rem;
		padding: 7px 14px;
		border-radius: 999px;
		border: 1px solid var(--accent);
		background: var(--bg-surface);
		color: var(--accent);
		cursor: pointer;
		transition:
			background var(--transition-fast),
			color var(--transition-fast),
			border-color var(--transition-fast),
			transform var(--transition-fast);
	}

	.option:hover:not(:disabled) {
		background: var(--accent);
		color: white;
		transform: translateY(-1px);
	}

	.option:disabled {
		cursor: default;
		opacity: 0.65;
	}

	.option.selected {
		background: var(--accent);
		color: white;
		border-color: var(--accent);
		opacity: 1;
	}

	.option-other {
		border-style: dashed;
		color: var(--text-muted);
		border-color: var(--border-strong);
	}

	.option-other:hover:not(:disabled) {
		background: var(--bg-inset);
		color: var(--text);
		border-color: var(--text-muted);
		transform: translateY(-1px);
	}

	.other-input-row {
		display: flex;
		gap: 6px;
		align-items: center;
	}

	.other-input {
		flex: 1;
		appearance: none;
		font: inherit;
		font-size: 0.875rem;
		padding: 7px 12px;
		border-radius: 999px;
		border: 1px solid var(--accent);
		background: var(--bg-surface);
		color: var(--text);
		outline: none;
		transition: border-color var(--transition-fast);
	}

	.other-input:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 3px var(--accent-subtle);
	}

	.other-submit,
	.other-cancel {
		appearance: none;
		font: inherit;
		font-size: 0.8125rem;
		padding: 6px 12px;
		border-radius: 999px;
		border: 1px solid transparent;
		cursor: pointer;
		transition:
			background var(--transition-fast),
			color var(--transition-fast),
			border-color var(--transition-fast);
	}

	.other-submit {
		background: var(--accent);
		color: white;
		border-color: var(--accent);
	}

	.other-submit:hover:not(:disabled) {
		filter: brightness(1.05);
	}

	.other-submit:disabled {
		opacity: 0.5;
		cursor: default;
	}

	.other-cancel {
		background: transparent;
		color: var(--text-muted);
		border-color: var(--border);
	}

	.other-cancel:hover {
		color: var(--text);
		border-color: var(--text-muted);
	}

	.answered-note {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.answered-note strong {
		color: var(--text);
		font-weight: 600;
	}
</style>
