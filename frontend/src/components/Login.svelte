<script lang="ts">
	let {
		onLogin,
		error = ''
	}: {
		onLogin: (email: string, displayName?: string) => Promise<void>;
		error?: string;
	} = $props();

	let email = $state('');
	let displayName = $state('');
	let loading = $state(false);
	let localError = $state('');

	let displayError = $derived(error || localError);

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		localError = '';
		const trimmedEmail = email.trim();
		if (!trimmedEmail) {
			localError = 'Email is required';
			return;
		}
		loading = true;
		try {
			await onLogin(trimmedEmail, displayName.trim() || undefined);
		} catch (err) {
			localError = err instanceof Error ? err.message : 'Login failed';
		} finally {
			loading = false;
		}
	}
</script>

<div class="login-container">
	<div class="login-card">
		<div class="login-header">
			<h1>Claude Chat</h1>
			<p class="subtitle">Sign in to start a conversation</p>
		</div>

		<form class="login-form" onsubmit={handleSubmit}>
			<label>
				<span class="label-text">Email</span>
				<input type="email" bind:value={email} placeholder="you@example.com" required />
			</label>

			<label>
				<span class="label-text">Display name <span class="optional">optional</span></span>
				<input type="text" bind:value={displayName} placeholder="Your name" />
			</label>

			{#if displayError}
				<p class="error">{displayError}</p>
			{/if}

			<button type="submit" class="login-btn" disabled={loading}>
				{loading ? 'Signing in...' : 'Sign in'}
				{#if !loading}
					<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
						<path d="M3 8H13M13 8L9 4M13 8L9 12" />
					</svg>
				{/if}
			</button>
		</form>
	</div>
</div>

<style>
	.login-container {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 100%;
		height: 100%;
		/* Subtle warm radial gradient — builds on token palette */
		background:
			radial-gradient(ellipse 70% 60% at 50% 35%, rgba(184, 90, 71, 0.055) 0%, transparent 70%),
			var(--bg);
		padding: 24px;
	}

	:global([data-theme='dark']) .login-container {
		background:
			radial-gradient(ellipse 70% 60% at 50% 35%, rgba(196, 106, 85, 0.08) 0%, transparent 70%),
			var(--bg);
	}

	.login-card {
		width: 100%;
		max-width: 380px;
	}

	.login-header {
		text-align: center;
		margin-bottom: 28px;
	}

	h1 {
		font-family: var(--font-display);
		font-size: 2.125rem;
		font-weight: 500;
		font-style: italic;
		color: var(--text);
		letter-spacing: -0.025em;
		margin-bottom: 7px;
		font-optical-sizing: auto;
	}

	.subtitle {
		color: var(--text-muted);
		font-size: 0.9375rem;
	}

	.login-form {
		display: flex;
		flex-direction: column;
		gap: 18px;
		padding: 30px;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius-xl);
		box-shadow: var(--shadow-lg), 0 0 0 1px rgba(184, 90, 71, 0.04);
	}

	label {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.label-text {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-secondary);
		letter-spacing: 0.01em;
	}

	.optional {
		font-weight: 400;
		color: var(--text-dim);
		font-style: italic;
	}

	input {
		padding: 10px 14px;
		background: var(--bg-inset);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		color: var(--text);
		font: inherit;
		font-size: 0.9375rem;
		outline: none;
		transition: border-color var(--transition-base), box-shadow var(--transition-base);
	}

	input:focus {
		border-color: var(--accent);
		box-shadow: var(--shadow-glow);
		background: var(--bg-surface);
	}

	input::placeholder {
		color: var(--text-dim);
	}

	.error {
		color: var(--error);
		font-size: 0.8125rem;
		text-align: center;
		padding: 8px 12px;
		background: var(--error-bg);
		border-radius: var(--radius-sm);
	}

	.login-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 6px;
		padding: 11px 20px;
		background: var(--accent);
		color: white;
		border-radius: var(--radius);
		font-size: 0.9375rem;
		font-weight: 600;
		letter-spacing: 0.01em;
		transition: background var(--transition-fast), box-shadow var(--transition-fast), transform var(--transition-fast);
		box-shadow: var(--shadow-sm);
		margin-top: 4px;
	}

	.login-btn:hover:not(:disabled) {
		background: var(--accent-hover);
		box-shadow: var(--shadow-md);
		transform: translateY(-0.5px);
	}

	.login-btn:active:not(:disabled) {
		transform: translateY(0);
	}

	.login-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
		transform: none;
	}
</style>
