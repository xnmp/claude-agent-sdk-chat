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
		onRename,
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
		onRename: (id: string, title: string) => void;
		user: User;
		onLogout: () => void;
		settings: Settings;
		onSettingsChange: (settings: Settings) => void;
	} = $props();

	let sidebarWidth = $state(280);
	let collapsed = $state(false);
	let isResizing = $state(false);

	// Inline rename — exactly one conversation can be in edit mode at a time.
	let editingId = $state<string | null>(null);
	let editingDraft = $state('');

	function startRename(id: string, currentTitle: string | null) {
		editingId = id;
		editingDraft = currentTitle ?? '';
	}

	function commitRename() {
		if (editingId === null) return;
		const trimmed = editingDraft.trim();
		const original = conversations.find((c) => c.id === editingId)?.title ?? '';
		// Empty input or unchanged → cancel without API call
		if (trimmed && trimmed !== original) {
			onRename(editingId, trimmed);
		}
		editingId = null;
		editingDraft = '';
	}

	function cancelRename() {
		editingId = null;
		editingDraft = '';
	}

	function handleRenameKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault();
			commitRename();
		} else if (e.key === 'Escape') {
			e.preventDefault();
			cancelRename();
		}
	}

	function startResize(e: MouseEvent) {
		e.preventDefault();
		isResizing = true;
		document.body.style.cursor = 'col-resize';
		document.body.style.userSelect = 'none';
		const onMove = (ev: MouseEvent) => {
			sidebarWidth = Math.max(200, Math.min(500, ev.clientX));
		};
		const onUp = () => {
			isResizing = false;
			document.body.style.cursor = '';
			document.body.style.userSelect = '';
			window.removeEventListener('mousemove', onMove);
			window.removeEventListener('mouseup', onUp);
		};
		window.addEventListener('mousemove', onMove);
		window.addEventListener('mouseup', onUp);
	}

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

<aside class="sidebar" class:collapsed class:resizing={isResizing} style="width: {collapsed ? 0 : sidebarWidth}px; min-width: {collapsed ? 0 : sidebarWidth}px">
	{#if !collapsed}
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
				class:editing={conv.id === editingId}
				role="button"
				tabindex="0"
				onclick={() => editingId !== conv.id && onSelect(conv.id)}
				onkeydown={(e) => editingId !== conv.id && e.key === 'Enter' && onSelect(conv.id)}
			>
				{#if editingId === conv.id}
					<!-- svelte-ignore a11y_autofocus -->
					<input
						class="rename-input"
						type="text"
						bind:value={editingDraft}
						onkeydown={handleRenameKeydown}
						onblur={commitRename}
						onclick={(e) => e.stopPropagation()}
						autofocus
						aria-label="Rename conversation"
					/>
				{:else}
					<span class="conv-title">{conv.title || 'New conversation'}</span>
					<span class="conv-time">{formatDate(conv.updated_at)}</span>
					<button
						class="rename-btn"
						onclick={(e) => {
							e.stopPropagation();
							startRename(conv.id, conv.title);
						}}
						aria-label="Rename conversation"
					>
						<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
							<path d="M8.5 1.5L10.5 3.5L4 10H2V8L8.5 1.5Z" />
						</svg>
					</button>
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
				{/if}
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
	{/if}
</aside>
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	class="resize-handle"
	class:collapsed
	onmousedown={collapsed ? null : startResize}
>
	<button class="collapse-btn" onclick={() => (collapsed = !collapsed)} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
		<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
			{#if collapsed}
				<polyline points="4,2 8,6 4,10" />
			{:else}
				<polyline points="8,2 4,6 8,10" />
			{/if}
		</svg>
	</button>
</div>

<style>
	.sidebar {
		background: var(--sidebar-bg);
		border-right: 1px solid var(--border);
		display: flex;
		flex-direction: column;
		overflow: hidden;
		transition: width 0.15s ease, min-width 0.15s ease;
	}

	.sidebar.collapsed {
		border-right: none;
	}

	.sidebar.resizing {
		transition: none;
	}

	.resize-handle {
		width: 6px;
		cursor: col-resize;
		background: transparent;
		display: flex;
		align-items: center;
		justify-content: center;
		position: relative;
		flex-shrink: 0;
		transition: background var(--transition-fast);
	}

	.resize-handle:hover {
		background: var(--border);
	}

	.resize-handle.collapsed {
		cursor: default;
		width: 20px;
	}

	.collapse-btn {
		position: absolute;
		width: 20px;
		height: 28px;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		color: var(--text-dim);
		opacity: 0;
		transition: opacity var(--transition-fast), background var(--transition-fast);
		z-index: 10;
	}

	.resize-handle:hover .collapse-btn,
	.resize-handle.collapsed .collapse-btn {
		opacity: 1;
	}

	.collapse-btn:hover {
		color: var(--text);
		background: var(--bg-hover);
	}

	.sidebar-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 18px 16px 14px;
		gap: 8px;
	}

	h2 {
		font-family: var(--font-display);
		font-size: 1.0625rem;
		font-weight: 500;
		font-style: italic;
		color: var(--text-secondary);
		letter-spacing: -0.01em;
		font-optical-sizing: auto;
	}

	.new-btn {
		display: flex;
		align-items: center;
		gap: 5px;
		padding: 6px 13px;
		border-radius: var(--radius);
		background: var(--accent);
		color: white;
		font-size: 0.8125rem;
		font-weight: 600;
		letter-spacing: 0.01em;
		transition: background var(--transition-fast), box-shadow var(--transition-fast), transform var(--transition-fast);
		box-shadow: var(--shadow-sm);
		flex-shrink: 0;
	}

	.new-btn:hover {
		background: var(--accent-hover);
		box-shadow: var(--shadow-md);
		transform: translateY(-0.5px);
	}

	.new-btn:active {
		transform: translateY(0);
		box-shadow: var(--shadow-sm);
	}

	.conversation-list {
		flex: 1;
		overflow-y: auto;
		padding: 2px 8px 8px;
	}

	.conversation-item {
		display: flex;
		align-items: center;
		gap: 8px;
		width: 100%;
		padding: 9px 10px 9px 12px;
		border-radius: var(--radius);
		text-align: left;
		transition: background var(--transition-fast);
		position: relative;
		cursor: pointer;
	}

	/* Left accent bar on active item */
	.conversation-item::before {
		content: '';
		position: absolute;
		left: 0;
		top: 50%;
		transform: translateY(-50%) scaleY(0);
		width: 3px;
		height: 60%;
		border-radius: 0 2px 2px 0;
		background: var(--accent);
		transition: transform var(--transition-fast);
	}

	.conversation-item:hover {
		background: var(--bg-hover);
	}

	.conversation-item.active {
		background: var(--bg-active);
	}

	.conversation-item.active::before {
		transform: translateY(-50%) scaleY(1);
	}

	.conv-title {
		flex: 1;
		font-size: 0.875rem;
		font-weight: 450;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		color: var(--text-secondary);
		transition: color var(--transition-fast);
	}

	.conversation-item.active .conv-title {
		color: var(--text);
		font-weight: 500;
	}

	.conversation-item:hover .conv-title {
		color: var(--text);
	}

	.conv-time {
		font-size: 0.6875rem;
		color: var(--text-dim);
		white-space: nowrap;
		font-variant-numeric: tabular-nums;
		letter-spacing: 0.01em;
	}

	.delete-btn,
	.rename-btn {
		opacity: 0;
		color: var(--text-dim);
		padding: 3px;
		border-radius: var(--radius-sm);
		transition: opacity var(--transition-fast), color var(--transition-fast), background var(--transition-fast);
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}

	.delete-btn:hover {
		color: var(--error);
		background: var(--error-bg);
		opacity: 1;
	}

	.rename-btn:hover {
		color: var(--accent);
		background: var(--accent-subtle);
		opacity: 1;
	}

	.conversation-item:hover .delete-btn,
	.conversation-item:hover .rename-btn,
	.conversation-item.active .delete-btn,
	.conversation-item.active .rename-btn {
		opacity: 0.7;
	}

	.conversation-item:hover .delete-btn:hover,
	.conversation-item:hover .rename-btn:hover {
		opacity: 1;
	}

	.conversation-item.editing {
		background: var(--bg-active);
	}

	.rename-input {
		flex: 1;
		min-width: 0;
		font: inherit;
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text);
		background: var(--bg-surface);
		border: 1px solid var(--border-strong);
		border-radius: var(--radius-sm);
		padding: 4px 8px;
		outline: none;
	}

	.rename-input:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--accent-subtle);
	}

	.empty {
		padding: 32px 16px;
		text-align: center;
		color: var(--text-dim);
		font-size: 0.875rem;
		font-family: var(--font-display);
		font-style: italic;
		font-optical-sizing: auto;
	}

	.sidebar-footer {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 12px 16px;
		border-top: 1px solid var(--border);
		gap: 8px;
	}

	.user-info {
		display: flex;
		align-items: center;
		gap: 9px;
		min-width: 0;
	}

	.user-avatar {
		width: 27px;
		height: 27px;
		border-radius: 50%;
		background: var(--accent-muted);
		color: var(--accent);
		font-size: 0.6875rem;
		font-weight: 700;
		letter-spacing: 0.02em;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
		border: 1.5px solid var(--accent-subtle);
	}

	.user-name {
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--text-secondary);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.footer-actions {
		display: flex;
		align-items: center;
		gap: 2px;
		flex-shrink: 0;
	}

	.logout-btn {
		font-size: 0.75rem;
		color: var(--text-dim);
		padding: 5px 9px;
		border-radius: var(--radius-sm);
		transition: color var(--transition-fast), background var(--transition-fast);
		flex-shrink: 0;
		letter-spacing: 0.01em;
	}

	.logout-btn:hover {
		color: var(--text);
		background: var(--bg-hover);
	}
</style>
