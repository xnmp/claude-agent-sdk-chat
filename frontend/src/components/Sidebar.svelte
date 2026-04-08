<script lang="ts">
	import type { Conversation, User } from '$lib/types';
	import type { Settings } from '$lib/settings';
	import SettingsMenu from './SettingsMenu.svelte';

	let {
		conversations,
		activeConversationId,
		onSelect,
		onNew,
		onDelete,
		user,
		onLogout,
		settings,
		onSettingsChange
	}: {
		conversations: Conversation[];
		activeConversationId: string | null;
		onSelect: (id: string) => void;
		onNew: () => void;
		onDelete: (id: string) => void;
		user: User;
		onLogout: () => void;
		settings: Settings;
		onSettingsChange: (settings: Settings) => void;
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
		<h2>Conversations</h2>
		<button class="new-btn" onclick={onNew}>
			<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
				<line x1="7" y1="2" x2="7" y2="12" />
				<line x1="2" y1="7" x2="12" y2="7" />
			</svg>
			New
		</button>
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
					aria-label="Delete conversation"
				>
					<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
						<line x1="2" y1="2" x2="10" y2="10" />
						<line x1="10" y1="2" x2="2" y2="10" />
					</svg>
				</button>
			</div>
		{/each}
		{#if conversations.length === 0}
			<p class="empty">No conversations yet</p>
		{/if}
	</div>
	<div class="sidebar-footer">
		<div class="user-info">
			<div class="user-avatar">{(user.display_name || user.email).charAt(0).toUpperCase()}</div>
			<span class="user-name">{user.display_name || user.email}</span>
		</div>
		<div class="footer-actions">
			<SettingsMenu {settings} onChange={onSettingsChange} />
			<button class="logout-btn" onclick={onLogout}>Sign out</button>
		</div>
	</div>
</aside>

<style>
	.sidebar {
		width: 300px;
		min-width: 300px;
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
		padding: 20px 20px 16px;
	}

	h2 {
		font-family: var(--font-display);
		font-size: 1.125rem;
		font-weight: 400;
		font-style: italic;
		color: var(--text);
		letter-spacing: -0.01em;
	}

	.new-btn {
		display: flex;
		align-items: center;
		gap: 5px;
		padding: 7px 14px;
		border-radius: var(--radius);
		background: var(--text);
		color: var(--bg-surface);
		font-size: 0.8125rem;
		font-weight: 600;
		letter-spacing: 0.01em;
		transition: all 0.15s ease;
		box-shadow: var(--shadow-sm);
	}

	.new-btn:hover {
		background: var(--text-secondary);
		box-shadow: var(--shadow-md);
		transform: translateY(-0.5px);
	}

	.conversation-list {
		flex: 1;
		overflow-y: auto;
		padding: 4px 12px;
	}

	.conversation-item {
		display: flex;
		align-items: center;
		gap: 8px;
		width: 100%;
		padding: 10px 12px;
		border-radius: var(--radius);
		text-align: left;
		transition: all 0.12s ease;
		position: relative;
		border: 1px solid transparent;
	}

	.conversation-item:hover {
		background: var(--bg-hover);
	}

	.conversation-item.active {
		background: var(--bg-active);
		border-color: var(--border);
		box-shadow: var(--shadow-sm);
	}

	.conv-title {
		flex: 1;
		font-size: 0.875rem;
		font-weight: 500;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		color: var(--text);
	}

	.conversation-item.active .conv-title {
		color: var(--text);
	}

	.conv-time {
		font-size: 0.6875rem;
		color: var(--text-dim);
		white-space: nowrap;
		font-variant-numeric: tabular-nums;
	}

	.delete-btn {
		opacity: 0;
		color: var(--text-dim);
		padding: 4px;
		border-radius: var(--radius-sm);
		transition: all 0.12s ease;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.delete-btn:hover {
		color: var(--error);
		background: var(--error-bg);
	}

	.conversation-item:hover .delete-btn {
		opacity: 1;
	}

	.empty {
		padding: 24px 16px;
		text-align: center;
		color: var(--text-dim);
		font-size: 0.875rem;
		font-style: italic;
	}

	.sidebar-footer {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 14px 20px;
		border-top: 1px solid var(--border);
	}

	.user-info {
		display: flex;
		align-items: center;
		gap: 10px;
		min-width: 0;
	}

	.user-avatar {
		width: 28px;
		height: 28px;
		border-radius: 50%;
		background: var(--accent-subtle);
		color: var(--accent);
		font-size: 0.75rem;
		font-weight: 600;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}

	.user-name {
		font-size: 0.8125rem;
		color: var(--text-secondary);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.footer-actions {
		display: flex;
		align-items: center;
		gap: 4px;
		flex-shrink: 0;
	}

	.logout-btn {
		font-size: 0.75rem;
		color: var(--text-muted);
		padding: 5px 10px;
		border-radius: var(--radius-sm);
		transition: all 0.15s ease;
		flex-shrink: 0;
	}

	.logout-btn:hover {
		color: var(--text);
		background: var(--bg-hover);
	}
</style>
