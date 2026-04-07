<script lang="ts">
	import type { Conversation } from '$lib/types';

	let {
		conversations,
		activeConversationId,
		onSelect,
		onNew,
		onDelete
	}: {
		conversations: Conversation[];
		activeConversationId: string | null;
		onSelect: (id: string) => void;
		onNew: () => void;
		onDelete: (id: string) => void;
	} = $props();

	function formatDate(iso: string): string {
		const d = new Date(iso);
		const now = new Date();
		const diffMs = now.getTime() - d.getTime();
		const diffMins = Math.floor(diffMs / 60000);
		if (diffMins < 1) return 'just now';
		if (diffMins < 60) return `${diffMins}m ago`;
		const diffHours = Math.floor(diffMins / 60);
		if (diffHours < 24) return `${diffHours}h ago`;
		const diffDays = Math.floor(diffHours / 24);
		if (diffDays < 7) return `${diffDays}d ago`;
		return d.toLocaleDateString();
	}
</script>

<aside class="sidebar">
	<div class="sidebar-header">
		<h2>Chats</h2>
		<button class="new-btn" onclick={onNew}>+ New</button>
	</div>
	<div class="conversation-list">
		{#each conversations as conv (conv.id)}
			<div
				class="conversation-item"
				class:active={conv.id === activeConversationId}
				role="button"
				tabindex="0"
				onclick={() => onSelect(conv.id)}
				onkeydown={(e) => e.key === 'Enter' && onSelect(conv.id)}
			>
				<span class="conv-title">{conv.title || 'New conversation'}</span>
				<span class="conv-time">{formatDate(conv.updated_at)}</span>
				<button
					class="delete-btn"
					onclick={(e) => {
						e.stopPropagation();
						onDelete(conv.id);
					}}
				>
					&times;
				</button>
			</div>
		{/each}
		{#if conversations.length === 0}
			<p class="empty">No conversations yet</p>
		{/if}
	</div>
</aside>

<style>
	.sidebar {
		width: 280px;
		min-width: 280px;
		background: var(--bg-surface);
		border-right: 1px solid var(--border);
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.sidebar-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 16px;
		border-bottom: 1px solid var(--border);
	}

	h2 {
		font-size: 0.875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
	}

	.new-btn {
		padding: 6px 12px;
		border-radius: var(--radius);
		background: var(--accent);
		color: white;
		font-size: 0.8125rem;
		font-weight: 500;
		transition: background 0.15s;
	}

	.new-btn:hover {
		background: var(--accent-dim);
	}

	.conversation-list {
		flex: 1;
		overflow-y: auto;
		padding: 8px;
	}

	.conversation-item {
		display: flex;
		align-items: center;
		gap: 8px;
		width: 100%;
		padding: 10px 12px;
		border-radius: var(--radius);
		text-align: left;
		transition: background 0.1s;
		position: relative;
	}

	.conversation-item:hover {
		background: var(--bg-hover);
	}

	.conversation-item.active {
		background: var(--bg-active);
	}

	.conv-title {
		flex: 1;
		font-size: 0.875rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.conv-time {
		font-size: 0.75rem;
		color: var(--text-dim);
		white-space: nowrap;
	}

	.delete-btn {
		opacity: 0;
		font-size: 1.1rem;
		color: var(--text-dim);
		padding: 2px 4px;
		border-radius: 4px;
		transition:
			opacity 0.1s,
			color 0.1s;
	}

	.delete-btn:hover {
		color: var(--error);
	}

	.conversation-item:hover .delete-btn {
		opacity: 1;
	}

	.empty {
		padding: 16px;
		text-align: center;
		color: var(--text-dim);
		font-size: 0.875rem;
	}
</style>
