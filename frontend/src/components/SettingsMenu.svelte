<script lang="ts">
	import type { Settings } from '$lib/settings';

	let {
		settings,
		onChange
	}: {
		settings: Settings;
		onChange: (settings: Settings) => void;
	} = $props();

	let open = $state(false);
	let btnEl: HTMLButtonElement | undefined = $state();
	let menuStyle = $state('');

	function toggle(key: 'showCost' | 'showDuration') {
		onChange({ ...settings, [key]: !settings[key] });
	}

	function setTheme(theme: 'light' | 'dark') {
		onChange({ ...settings, theme });
	}
</script>

<div class="settings-wrapper">
	<button class="settings-btn" bind:this={btnEl} onclick={() => {
		if (!open && btnEl) {
			const rect = btnEl.getBoundingClientRect();
			menuStyle = `left: ${rect.left}px; bottom: ${window.innerHeight - rect.top + 8}px;`;
		}
		open = !open;
	}} aria-label="Settings">
		<svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
			<circle cx="9" cy="9" r="2.5" />
			<path d="M7.5 2.5L8 1h2l.5 1.5.8.3L13 2l1.4 1.4-1 1.7.3.8L15.5 7v2l-1.5.5-.3.8 1 1.7L13.3 13.4l-1.7-1-.8.3L10.5 15h-2l-.5-1.5-.8-.3-1.7 1L4 12.8l1-1.7-.3-.8L2.5 10V8l1.5-.5.3-.8-1-1.7L4.7 3.6l1.7 1z" />
		</svg>
	</button>

	{#if open}
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="backdrop" onclick={() => (open = false)}></div>
		<div class="menu" style={menuStyle}>
			<div class="menu-header">Settings</div>

			<div class="menu-section">
				<div class="section-label">Theme</div>
				<div class="theme-toggle">
					<button
						class="theme-btn"
						class:active={settings.theme === 'light'}
						onclick={() => setTheme('light')}
					>Light</button>
					<button
						class="theme-btn"
						class:active={settings.theme === 'dark'}
						onclick={() => setTheme('dark')}
					>Dark</button>
				</div>
			</div>

			<div class="menu-section">
				<div class="section-label">Display</div>
				<label class="toggle-row">
					<span>Show cost</span>
					<input type="checkbox" checked={settings.showCost} onchange={() => toggle('showCost')} />
				</label>
				<label class="toggle-row">
					<span>Show duration</span>
					<input type="checkbox" checked={settings.showDuration} onchange={() => toggle('showDuration')} />
				</label>
			</div>
		</div>
	{/if}
</div>

<style>
	.settings-wrapper {
		position: relative;
		z-index: 100;
	}

	.settings-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 30px;
		height: 30px;
		border-radius: var(--radius-sm);
		color: var(--text-dim);
		transition: color var(--transition-fast), background var(--transition-fast);
	}

	.settings-btn:hover {
		background: var(--bg-hover);
		color: var(--text-secondary);
	}

	.backdrop {
		position: fixed;
		inset: 0;
		z-index: 99;
	}

	.menu {
		position: fixed;
		width: 220px;
		max-height: calc(100vh - 80px);
		overflow-y: auto;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		box-shadow: var(--shadow-lg);
		z-index: 100;
		padding: 8px 0;
	}

	.menu-header {
		padding: 8px 14px;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.menu-section {
		padding: 6px 14px;
		border-top: 1px solid var(--border);
	}

	.section-label {
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--text-dim);
		margin-bottom: 6px;
		margin-top: 4px;
	}

	.theme-toggle {
		display: flex;
		gap: 4px;
		margin-bottom: 4px;
	}

	.theme-btn {
		flex: 1;
		padding: 5px 0;
		font-size: 0.8125rem;
		border-radius: var(--radius-sm);
		border: 1px solid var(--border);
		color: var(--text-secondary);
		transition: all 0.15s ease;
	}

	.theme-btn:hover {
		background: var(--bg-hover);
	}

	.theme-btn.active {
		background: var(--accent-subtle);
		border-color: var(--accent);
		color: var(--accent);
		font-weight: 600;
	}

	.toggle-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 4px 0;
		font-size: 0.8125rem;
		color: var(--text-secondary);
		cursor: pointer;
	}

	.toggle-row input[type='checkbox'] {
		accent-color: var(--accent);
		width: 15px;
		height: 15px;
	}
</style>
