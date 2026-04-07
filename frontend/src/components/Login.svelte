<script lang="ts">
	import type { User } from '$lib/types';
	import { login } from '$lib/api';

	let { onLogin }: { onLogin: (user: User) => void } = $props();

	let email = $state('');
	let displayName = $state('');
	let error = $state('');
	let loading = $state(false);

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		const trimmedEmail = email.trim();
		if (!trimmedEmail) {
			error = 'Email is required';
			return;
		}
		loading = true;
		try {
			const user = await login(trimmedEmail, displayName.trim() || undefined);
			localStorage.setItem('user', JSON.stringify(user));
			onLogin(user);
		} catch {
			error = 'Login failed. Is the backend running?';
		} finally {
			loading = false;
		}
	}
</script>

<div class="login-container">
	<form class="login-form" onsubmit={handleSubmit}>
		<h1>Claude Chat</h1>
		<p class="subtitle">Sign in to start chatting</p>

		<label>
			<span>Email</span>
			<input type="email" bind:value={email} placeholder="you@example.com" required />
		</label>

		<label>
			<span>Display name <span class="optional">(optional)</span></span>
			<input type="text" bind:value={displayName} placeholder="Your name" />
		</label>

		{#if error}
			<p class="error">{error}</p>
		{/if}

		<button type="submit" class="login-btn" disabled={loading}>
			{loading ? 'Signing in...' : 'Sign in'}
		</button>
	</form>
</div>

<style>
	.login-container {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 100%;
		height: 100%;
		background: var(--bg);
	}

	.login-form {
		display: flex;
		flex-direction: column;
		gap: 1rem;
		width: 100%;
		max-width: 360px;
		padding: 2.5rem;
		background: var(--bg-surface);
		border: 1px solid var(--border);
		border-radius: var(--radius);
	}

	h1 {
		font-size: 1.5rem;
		font-weight: 600;
		text-align: center;
		color: var(--text);
	}

	.subtitle {
		text-align: center;
		color: var(--text-muted);
		font-size: 0.875rem;
		margin-bottom: 0.5rem;
	}

	label {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		font-size: 0.85rem;
		color: var(--text-muted);
	}

	.optional {
		color: var(--text-dim);
	}

	input {
		padding: 0.6rem 0.75rem;
		background: var(--bg);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		color: var(--text);
		font-size: 0.9rem;
		outline: none;
		transition: border-color 0.15s;
	}

	input:focus {
		border-color: var(--accent);
	}

	.error {
		color: var(--error);
		font-size: 0.85rem;
		text-align: center;
	}

	.login-btn {
		padding: 0.65rem;
		background: var(--accent);
		color: white;
		border-radius: var(--radius);
		font-size: 0.9rem;
		font-weight: 500;
		transition: background 0.15s;
		margin-top: 0.25rem;
	}

	.login-btn:hover:not(:disabled) {
		background: var(--accent-dim);
	}

	.login-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}
</style>
