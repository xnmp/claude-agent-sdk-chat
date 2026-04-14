<script lang="ts">
	interface TodoItem {
		content: string;
		status: 'pending' | 'in_progress' | 'completed';
		activeForm: string;
	}

	let { todos }: { todos: TodoItem[] } = $props();

	let total = $derived(todos.length);
	let completedCount = $derived(todos.filter((t) => t.status === 'completed').length);
	let allDone = $derived(total > 0 && completedCount === total);
</script>

<div class="todo-list" class:all-done={allDone}>
	<div class="todo-header">
		<svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
			<rect x="2" y="2" width="10" height="10" rx="2" />
			<path d="M4.5 7.25L6.25 9L9.5 5.5" />
		</svg>
		<span class="todo-title">Todo list</span>
		<span class="todo-count">{completedCount}/{total}</span>
	</div>
	<ul>
		{#each todos as todo, i (i)}
			<li class="todo-item status-{todo.status}">
				<span class="todo-icon">
					{#if todo.status === 'completed'}
						<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
							<circle cx="7" cy="7" r="6" fill="currentColor" stroke="none" />
							<path d="M4 7.25L6 9.25L10 5" stroke="var(--bg-surface)" />
						</svg>
					{:else if todo.status === 'in_progress'}
						<span class="spinner" aria-hidden="true"></span>
					{:else}
						<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5">
							<circle cx="7" cy="7" r="5.5" />
						</svg>
					{/if}
				</span>
				<span class="todo-text">
					{todo.status === 'in_progress' ? todo.activeForm : todo.content}
				</span>
			</li>
		{/each}
	</ul>
</div>

<style>
	.todo-list {
		border-radius: var(--radius);
		background: var(--tool-bg);
		border: 1px solid var(--tool-border);
		padding: 10px 13px 11px;
		transition: border-color var(--transition-base), background var(--transition-base);
	}

	.todo-list.all-done {
		border-color: var(--success-bg);
	}

	.todo-header {
		display: flex;
		align-items: center;
		gap: 7px;
		padding-bottom: 8px;
		margin-bottom: 6px;
		border-bottom: 1px solid var(--tool-border);
		color: var(--text-secondary);
	}

	.todo-header svg {
		color: var(--success);
		opacity: 0.8;
		flex-shrink: 0;
	}

	.todo-title {
		font-family: var(--font-mono);
		font-weight: 500;
		font-size: 0.8125rem;
		color: var(--text-secondary);
	}

	.todo-count {
		margin-left: auto;
		font-size: 0.625rem;
		font-weight: 700;
		padding: 2px 7px;
		border-radius: 8px;
		background: var(--success-bg);
		color: var(--success);
		letter-spacing: 0.04em;
		font-variant-numeric: tabular-nums;
	}

	ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.todo-item {
		display: flex;
		align-items: center;
		gap: 9px;
		padding: 4px 2px;
		font-size: 0.8125rem;
		line-height: 1.5;
		transition: color var(--transition-base);
	}

	.todo-icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 14px;
		height: 14px;
		flex-shrink: 0;
	}

	.todo-text {
		flex: 1;
		min-width: 0;
		transition: color var(--transition-base), text-decoration-color var(--transition-base), opacity var(--transition-base);
	}

	.status-pending .todo-icon {
		color: var(--text-dim);
	}
	.status-pending .todo-text {
		color: var(--text-muted);
	}

	.status-in_progress .todo-icon {
		color: var(--accent);
	}
	.status-in_progress .todo-text {
		color: var(--text);
		font-weight: 600;
	}

	.status-completed .todo-icon {
		color: var(--success);
	}
	.status-completed .todo-text {
		color: var(--text-dim);
		text-decoration: line-through;
		text-decoration-color: var(--text-dim);
		text-decoration-thickness: 1px;
		opacity: 0.75;
	}

	.spinner {
		width: 12px;
		height: 12px;
		border-radius: 50%;
		border: 1.5px solid var(--accent-muted);
		border-top-color: var(--accent);
		animation: spin 0.9s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}
</style>
