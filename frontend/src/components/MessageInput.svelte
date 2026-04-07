<script lang="ts">
	let {
		isStreaming,
		disabled,
		onSend,
		onInterrupt
	}: {
		isStreaming: boolean;
		disabled: boolean;
		onSend: (content: string) => void;
		onInterrupt: () => void;
	} = $props();

	let input = $state('');

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			submit();
		}
	}

	function submit() {
		const trimmed = input.trim();
		if (!trimmed || disabled || isStreaming) return;
		onSend(trimmed);
		input = '';
	}
</script>

<div class="input-area">
	<div class="input-wrapper">
		<textarea
			bind:value={input}
			onkeydown={handleKeydown}
			placeholder={disabled ? 'Select or create a conversation' : 'Send a message...'}
			disabled={disabled || isStreaming}
			rows={1}
		></textarea>
		{#if isStreaming}
			<button class="action-btn stop" onclick={onInterrupt}>Stop</button>
		{:else}
			<button class="action-btn send" onclick={submit} disabled={disabled || !input.trim()}>
				Send
			</button>
		{/if}
	</div>
	<p class="hint">Enter to send, Shift+Enter for newline</p>
</div>

<style>
	.input-area {
		padding: 16px 24px 12px;
		border-top: 1px solid var(--border);
	}

	.input-wrapper {
		display: flex;
		gap: 8px;
		align-items: flex-end;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		padding: 8px 12px;
		transition: border-color 0.15s;
	}

	.input-wrapper:focus-within {
		border-color: var(--accent);
	}

	textarea {
		flex: 1;
		border: none;
		background: none;
		color: var(--text);
		font: inherit;
		font-size: 0.9375rem;
		resize: none;
		outline: none;
		min-height: 24px;
		max-height: 200px;
		line-height: 1.5;
		field-sizing: content;
	}

	textarea::placeholder {
		color: var(--text-dim);
	}

	textarea:disabled {
		opacity: 0.5;
	}

	.action-btn {
		padding: 6px 14px;
		border-radius: 6px;
		font-size: 0.8125rem;
		font-weight: 500;
		transition: background 0.15s;
		flex-shrink: 0;
	}

	.send {
		background: var(--accent);
		color: white;
	}

	.send:hover:not(:disabled) {
		background: var(--accent-dim);
	}

	.send:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.stop {
		background: var(--error);
		color: white;
	}

	.stop:hover {
		opacity: 0.85;
	}

	.hint {
		text-align: center;
		font-size: 0.75rem;
		color: var(--text-dim);
		margin-top: 6px;
	}
</style>
