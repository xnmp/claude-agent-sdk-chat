<script lang="ts">
	import type { UploadResult } from '$lib/api';

	let {
		isStreaming,
		disabled,
		onSend,
		onInterrupt
	}: {
		isStreaming: boolean;
		disabled: boolean;
		onSend: (content: string, files: File[]) => void;
		onInterrupt: () => void;
	} = $props();

	let input = $state('');
	let attachedFiles = $state<File[]>([]);
	let fileInput: HTMLInputElement | undefined = $state();

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			submit();
		}
	}

	function submit() {
		const trimmed = input.trim();
		if ((!trimmed && attachedFiles.length === 0) || disabled || isStreaming) return;
		onSend(trimmed, attachedFiles);
		input = '';
		attachedFiles = [];
	}

	function handleFileSelect(e: Event) {
		const target = e.target as HTMLInputElement;
		if (target.files) {
			attachedFiles = [...attachedFiles, ...Array.from(target.files)];
		}
		// Reset input so the same file can be selected again
		target.value = '';
	}

	function removeFile(index: number) {
		attachedFiles = attachedFiles.filter((_, i) => i !== index);
	}

	function formatSize(bytes: number): string {
		if (bytes < 1024) return `${bytes}B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
	}
</script>

<div class="input-area">
	{#if attachedFiles.length > 0}
		<div class="attached-files">
			{#each attachedFiles as file, i}
				<div class="file-chip">
					<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
						<path d="M7 1H3C2.45 1 2 1.45 2 2V10C2 10.55 2.45 11 3 11H9C9.55 11 10 10.55 10 10V4L7 1Z" />
						<path d="M7 1V4H10" />
					</svg>
					<span class="file-name">{file.name}</span>
					<span class="file-size">{formatSize(file.size)}</span>
					<button class="remove-file" onclick={() => removeFile(i)} aria-label="Remove file">
						<svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
							<line x1="2" y1="2" x2="8" y2="8" />
							<line x1="8" y1="2" x2="2" y2="8" />
						</svg>
					</button>
				</div>
			{/each}
		</div>
	{/if}

	<div class="input-wrapper">
		<button
			class="attach-btn"
			onclick={() => fileInput?.click()}
			disabled={disabled || isStreaming}
			aria-label="Attach file"
		>
			<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
				<path d="M14 8.5L8.35 14.15C6.57 15.93 3.68 15.93 1.9 14.15C0.12 12.37 0.12 9.48 1.9 7.7L9.2 0.4C10.37 -0.77 12.28 -0.77 13.45 0.4C14.62 1.57 14.62 3.48 13.45 4.65L6.15 11.95C5.57 12.53 4.61 12.53 4.03 11.95C3.45 11.37 3.45 10.41 4.03 9.83L10.5 3.35" />
			</svg>
		</button>
		<input
			type="file"
			multiple
			bind:this={fileInput}
			onchange={handleFileSelect}
			style="display: none"
		/>
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
				<button class="action-btn send" onclick={submit} disabled={disabled || (!input.trim() && attachedFiles.length === 0)}>
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

	.attached-files {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		margin-bottom: 8px;
	}

	.file-chip {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		padding: 4px 8px;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		font-size: 0.75rem;
		color: var(--text-secondary);
	}

	.file-name {
		max-width: 150px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-family: var(--font-mono);
		font-size: 0.6875rem;
	}

	.file-size {
		color: var(--text-dim);
		font-size: 0.625rem;
	}

	.remove-file {
		display: flex;
		align-items: center;
		padding: 1px;
		color: var(--text-dim);
		border-radius: 3px;
		transition: all 0.12s ease;
	}

	.remove-file:hover {
		color: var(--error);
		background: var(--error-bg);
	}

	.input-wrapper {
		display: flex;
		gap: 8px;
		align-items: flex-end;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-lg);
		padding: 10px 12px 10px 12px;
		transition: all 0.2s ease;
		box-shadow: var(--shadow-md);
	}

	.input-wrapper:focus-within {
		border-color: var(--accent);
		box-shadow: var(--shadow-glow);
	}

	.attach-btn {
		flex-shrink: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		width: 32px;
		height: 32px;
		border-radius: var(--radius-sm);
		color: var(--text-muted);
		transition: all 0.15s ease;
	}

	.attach-btn:hover:not(:disabled) {
		background: var(--bg-hover);
		color: var(--text);
	}

	.attach-btn:disabled {
		opacity: 0.3;
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
