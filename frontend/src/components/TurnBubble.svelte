<script lang="ts">
	import type {
		Block,
		Message,
		UserContent,
		AssistantContent,
		LiveTurn,
		ToolCallBlock,
	} from "$lib/types";
	import type { Settings } from "$lib/settings";
	import StreamingMarkdown from "./StreamingMarkdown.svelte";
	import ToolCall from "./ToolCall.svelte";
	import QuestionPrompt from "./QuestionPrompt.svelte";

	let {
		message = null,
		liveTurn = null,
		isLive = false,
		settings = { theme: "light", showCost: true, showDuration: true },
		onAnswerQuestion = () => {},
	}: {
		message?: Message | null;
		liveTurn?: LiveTurn | null;
		isLive?: boolean;
		settings?: Settings;
		onAnswerQuestion?: (toolUseId: string, answer: string) => void;
	} = $props();

	// Elapsed timer — uses liveTurn.startedAt so it survives conversation switches
	let elapsedMs = $state(0);

	$effect(() => {
		if (!isLive || !liveTurn) return;
		const start = liveTurn.startedAt;
		elapsedMs = Date.now() - start;
		const timer = setInterval(() => {
			elapsedMs = Date.now() - start;
		}, 100);
		return () => clearInterval(timer);
	});

	let isUser = $derived(message?.role === "user");
	let userContent = $derived(
		isUser ? (message?.content as UserContent) : null,
	);
	let assistantContent = $derived(
		!isUser && message ? (message.content as AssistantContent) : null,
	);

	// Created-file relative paths are stored as "<session_id>/<name>" so the
	// /api/output static mount resolves them correctly. Strip a leading
	// UUID-shaped segment for display so users see the plain filename, while
	// the href and download attributes keep the full path.
	const SESSION_PREFIX =
		/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\//i;
	const displayFileLabel = (path: string) => path.replace(SESSION_PREFIX, "");

	// Source of truth for the block list, regardless of live vs persisted.
	let blocks = $derived<Block[]>(
		isLive && liveTurn ? liveTurn.blocks : (assistantContent?.blocks ?? []),
	);

	// Show a streaming dot indicator only when streaming and the model hasn't
	// emitted any text or tool yet.
	let showStreamingDots = $derived(isLive && blocks.length === 0);
	let lastToolCall = $derived.by((): ToolCallBlock | null => {
		for (let i = blocks.length - 1; i >= 0; i--) {
			const b = blocks[i];
			if (b.kind === "tool_call") return b;
		}
		return null;
	});
</script>

{#if isUser && userContent}
	<div class="turn user-turn">
		<div class="bubble user-bubble">
			<p>{userContent.text}</p>
		</div>
	</div>
{:else if isLive || assistantContent}
	<div class="turn assistant-turn">
		<div class="bubble assistant-bubble">
			{#each blocks as block, idx (idx)}
				{#if block.kind === "text"}
					<div class="response-text markdown">
						<StreamingMarkdown
							text={block.text}
							revealed={block.revealed}
						/>
					</div>
				{:else if block.kind === "thinking"}
					<details class="thinking-block">
						<summary>
							<svg
								width="14"
								height="14"
								viewBox="0 0 14 14"
								fill="none"
								stroke="currentColor"
								stroke-width="1.5"
								stroke-linecap="round"
							>
								<circle cx="7" cy="7" r="5.5" />
								<path
									d="M5.5 5.5C5.5 4.67 6.17 4 7 4C7.83 4 8.5 4.67 8.5 5.5C8.5 6.33 7.83 7 7 7V8"
								/>
								<circle
									cx="7"
									cy="9.5"
									r="0.5"
									fill="currentColor"
								/>
							</svg>
							Thinking
						</summary>
						<pre>{block.thinking}</pre>
					</details>
				{:else if block.kind === "tool_call"}
					<ToolCall tool={block} />
				{:else if block.kind === "question"}
					<QuestionPrompt question={block} onAnswer={onAnswerQuestion} />
				{/if}
			{/each}

			{#if showStreamingDots}
				<div class="streaming-indicator">
					<span class="dot"></span>
					<span class="dot"></span>
					<span class="dot"></span>
				</div>
			{:else if isLive && lastToolCall && lastToolCall.result === null}
				<div class="streaming-indicator">
					<span class="dot"></span>
					<span class="dot"></span>
					<span class="dot"></span>
					<span class="streaming-status">
						{typeof lastToolCall.input?.description === "string"
							? lastToolCall.input.description
							: lastToolCall.name}...
					</span>
				</div>
			{/if}

			{#if isLive && settings.showDuration && elapsedMs > 0}
				<div class="meta">
					<span>{(elapsedMs / 1000).toFixed(1)}s</span>
				</div>
			{:else if assistantContent && ((settings.showCost && assistantContent.total_cost_usd > 0) || (settings.showDuration && assistantContent.duration_ms > 0))}
				<div class="meta">
					{#if settings.showCost && assistantContent.total_cost_usd > 0}
						<span
							>${assistantContent.total_cost_usd.toFixed(4)}</span
						>
					{/if}
					{#if settings.showCost && settings.showDuration && assistantContent.total_cost_usd > 0 && assistantContent.duration_ms > 0}
						<span class="meta-sep">&middot;</span>
					{/if}
					{#if settings.showDuration && assistantContent.duration_ms > 0}
						<span
							>{(assistantContent.duration_ms / 1000).toFixed(
								1,
							)}s</span
						>
					{/if}
				</div>
			{/if}

			{#if assistantContent && assistantContent.created_files && assistantContent.created_files.length > 0}
				<div class="created-files">
					<span class="files-label">Files:</span>
					{#each assistantContent.created_files as file}
						<a
							class="file-link"
							href="http://localhost:8000/api/output/{file}"
							download={file.split("/").pop()}
							target="_blank"
						>
							<svg
								width="12"
								height="12"
								viewBox="0 0 12 12"
								fill="none"
								stroke="currentColor"
								stroke-width="1.5"
								stroke-linecap="round"
								stroke-linejoin="round"
							>
								<path d="M6 2v6M3 6l3 3 3-3M2 10h8" />
							</svg>
							{displayFileLabel(file)}
						</a>
					{/each}
				</div>
			{/if}
		</div>
	</div>
{/if}

<style>
	.turn {
		padding: 5px 0;
	}

	.bubble {
		max-width: 92%;
		padding: 14px 18px;
		border-radius: var(--radius-lg);
		line-height: 1.62;
		font-size: 0.9375rem;
	}

	/* User messages */
	.user-bubble {
		background: var(--accent);
		color: white;
		margin-left: auto;
		border-bottom-right-radius: 3px;
		box-shadow:
			0 1px 3px rgba(0, 0, 0, 0.12),
			0 1px 1px rgba(0, 0, 0, 0.06);
	}

	.user-bubble p {
		white-space: pre-wrap;
		word-break: break-word;
	}

	/* Assistant messages */
	.assistant-bubble {
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-bottom-left-radius: 3px;
		box-shadow: var(--shadow-sm);
	}

	.response-text {
		word-break: break-word;
	}

	/* Markdown typography */
	.response-text.markdown :global(p) {
		margin: 0 0 0.65em;
	}

	.response-text.markdown :global(p:last-child) {
		margin-bottom: 0;
	}

	.response-text.markdown :global(h1),
	.response-text.markdown :global(h2),
	.response-text.markdown :global(h3),
	.response-text.markdown :global(h4) {
		margin: 1em 0 0.4em;
		font-weight: 600;
		line-height: 1.3;
		letter-spacing: -0.01em;
	}

	.response-text.markdown :global(h1) {
		font-size: 1.3em;
	}
	.response-text.markdown :global(h2) {
		font-size: 1.15em;
	}
	.response-text.markdown :global(h3) {
		font-size: 1.05em;
	}

	.response-text.markdown :global(ul),
	.response-text.markdown :global(ol) {
		margin: 0.4em 0;
		padding-left: 1.5em;
	}

	.response-text.markdown :global(li) {
		margin: 0.25em 0;
	}

	.response-text.markdown :global(code) {
		font-family: var(--font-mono);
		font-size: 0.84em;
		background: var(--bg-inset);
		padding: 0.14em 0.38em;
		border-radius: 4px;
		border: 1px solid var(--border);
	}

	.response-text.markdown :global(pre) {
		margin: 0.7em 0;
		padding: 0.85em 1.05em;
		background: var(--bg-inset);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		overflow-x: auto;
	}

	.response-text.markdown :global(pre code) {
		background: none;
		padding: 0;
		border: none;
		font-size: 0.84em;
	}

	.response-text.markdown :global(blockquote) {
		margin: 0.6em 0;
		padding: 0.35em 0.9em;
		border-left: 2.5px solid var(--accent);
		color: var(--text-secondary);
		background: var(--accent-subtle);
		border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
	}

	.response-text.markdown :global(a) {
		color: var(--accent);
		text-decoration: underline;
		text-decoration-thickness: 1px;
		text-underline-offset: 2px;
	}

	.response-text.markdown :global(table) {
		border-collapse: collapse;
		margin: 0.6em 0;
		width: 100%;
		font-size: 0.9em;
	}

	.response-text.markdown :global(th),
	.response-text.markdown :global(td) {
		border: 1px solid var(--border);
		padding: 0.45em 0.75em;
		text-align: left;
	}

	.response-text.markdown :global(th) {
		font-weight: 600;
		background: var(--bg-inset);
		font-size: 0.8125em;
		letter-spacing: 0.02em;
		text-transform: uppercase;
	}

	.response-text.markdown :global(hr) {
		border: none;
		border-top: 1px solid var(--border);
		margin: 1em 0;
	}

	/* Per-block spacing */
	.bubble > :global(.response-text + .response-text),
	.bubble > :global(.response-text + .tool-call),
	.bubble > :global(.tool-call + .response-text),
	.bubble > :global(.tool-call + .tool-call),
	.bubble > :global(.thinking-block + .response-text),
	.bubble > :global(.response-text + .thinking-block),
	.bubble > :global(.tool-call + .thinking-block),
	.bubble > :global(.thinking-block + .tool-call) {
		margin-top: 10px;
	}

	/* Inline thinking block */
	.thinking-block {
		border-radius: var(--radius);
		background: var(--thinking-bg);
		border: 1px solid var(--thinking-border);
		overflow: hidden;
	}

	.thinking-block summary {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 8px 12px;
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--text-muted);
		cursor: pointer;
		user-select: none;
		transition: color var(--transition-fast);
	}

	.thinking-block summary:hover {
		color: var(--text-secondary);
	}

	.thinking-block summary::-webkit-details-marker {
		display: none;
	}
	.thinking-block summary::marker {
		content: "";
	}

	.thinking-block pre {
		padding: 0 12px 12px;
		white-space: pre-wrap;
		word-break: break-word;
		font-size: 0.8125rem;
		color: var(--text-muted);
		line-height: 1.6;
		margin: 0;
		border-top: 1px solid var(--thinking-border);
	}

	/* Meta info */
	.meta {
		display: flex;
		align-items: center;
		gap: 6px;
		margin-top: 10px;
		padding-top: 9px;
		border-top: 1px solid var(--border);
		font-size: 0.6875rem;
		color: var(--text-dim);
		font-variant-numeric: tabular-nums;
		letter-spacing: 0.02em;
	}

	.meta-sep {
		color: var(--border-strong);
	}

	/* Download links */
	.created-files {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 5px;
		margin-top: 8px;
		padding-top: 8px;
		border-top: 1px solid var(--border);
	}

	.files-label {
		font-size: 0.6875rem;
		color: var(--text-dim);
		font-weight: 600;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}

	.file-link {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		padding: 3px 9px 3px 7px;
		background: var(--accent-subtle);
		color: var(--accent);
		border: 1px solid var(--accent-muted);
		border-radius: var(--radius-sm);
		font-family: var(--font-mono);
		font-size: 0.6875rem;
		text-decoration: none;
		transition:
			background var(--transition-fast),
			border-color var(--transition-fast);
	}

	.file-link:hover {
		background: var(--accent-muted);
		border-color: var(--accent);
		text-decoration: none;
	}

	/* Streaming indicator */
	.streaming-indicator {
		display: flex;
		align-items: center;
		gap: 5px;
		padding: 4px 0 2px;
	}

	.streaming-status {
		font-size: 0.75rem;
		color: var(--text-dim);
		margin-left: 3px;
		font-style: italic;
	}

	.dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--accent);
		opacity: 0.3;
		animation: pulse 1.4s ease-in-out infinite;
	}

	.dot:nth-child(2) {
		animation-delay: 0.2s;
	}

	.dot:nth-child(3) {
		animation-delay: 0.4s;
	}

	@keyframes pulse {
		0%,
		80%,
		100% {
			opacity: 0.2;
			transform: scale(0.8);
		}
		40% {
			opacity: 1;
			transform: scale(1.1);
		}
	}
</style>
