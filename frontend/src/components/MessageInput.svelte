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
		<div class="actions">
			{#if isStreaming}
				<button class="action-btn stop" onclick={onInterrupt}>
					<svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
						<rect x="2" y="2" width="10" height="10" rx="2" />
					</svg>
					Stop
				</button>
			{:else}
				<button class="action-btn send" onclick={submit} disabled={disabled || !input.trim()}>
					Send
					<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
						<path d="M12 2L6 8" />
						<path d="M12 2L8 13L6 8L1 6L12 2Z" />
					</svg>
				</button>
			{/if}
		</div>
	</div>
	<p class="hint"><kbd>Enter</kbd> to send &middot; <kbd>Shift+Enter</kbd> for newline</p>
</div>

<style>
	.input-area {
		padding: 0 24px 16px;
		max-width: 768px;
		margin: 0 auto;
		width: 100%;
	}

	.input-wrapper {
		display: flex;
		gap: 10px;
		align-items: flex-end;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-lg);
		padding: 10px 12px 10px 16px;
		transition: all 0.2s ease;
		box-shadow: var(--shadow-md);
	}

	.input-wrapper:focus-within {
		border-color: var(--accent);
		box-shadow: var(--shadow-glow);
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
		line-height: 1.55;
		field-sizing: content;
	}

	textarea::placeholder {
		color: var(--text-dim);
	}

	textarea:disabled {
		opacity: 0.5;
	}

	.actions {
		flex-shrink: 0;
		display: flex;
		padding-bottom: 1px;
	}

	.action-btn {
		display: flex;
		align-items: center;
		gap: 5px;
		padding: 7px 14px;
		border-radius: var(--radius);
		font-size: 0.8125rem;
		font-weight: 600;
		letter-spacing: 0.01em;
		transition: all 0.15s ease;
	}

	.send {
		background: var(--accent);
		color: white;
		box-shadow: var(--shadow-sm);
	}

	.send:hover:not(:disabled) {
		background: var(--accent-hover);
		box-shadow: var(--shadow-md);
		transform: translateY(-0.5px);
	}

	.send:disabled {
		opacity: 0.35;
		cursor: not-allowed;
		transform: none;
		box-shadow: none;
	}

	.stop {
		background: var(--error-bg);
		color: var(--error);
	}

	.stop:hover {
		background: var(--error);
		color: white;
	}

	.hint {
		text-align: center;
		font-size: 0.6875rem;
		color: var(--text-dim);
		margin-top: 8px;
		letter-spacing: 0.02em;
	}

	kbd {
		font-family: var(--font-mono);
		font-size: 0.625rem;
		padding: 1px 5px;
		border-radius: 4px;
		border: 1px solid var(--border);
		background: var(--bg-inset);
	}
</style>
