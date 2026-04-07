import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import Login from '../src/components/Login.svelte';

describe('Login component', () => {
	afterEach(cleanup);

	it('renders email and display name fields', () => {
		render(Login, { props: { onLogin: vi.fn() } });
		expect(screen.getByPlaceholderText('you@example.com')).toBeInTheDocument();
		expect(screen.getByPlaceholderText('Your name')).toBeInTheDocument();
	});

	it('renders sign in button', () => {
		render(Login, { props: { onLogin: vi.fn() } });
		expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
	});

	it('shows error when submitting whitespace-only email', async () => {
		const user = userEvent.setup();
		render(Login, { props: { onLogin: vi.fn() } });

		const emailInput = screen.getByPlaceholderText('you@example.com');
		// Remove the required attribute so the form submits, then test our custom validation
		emailInput.removeAttribute('required');
		await user.type(emailInput, '   ');
		await user.click(screen.getByRole('button', { name: /sign in/i }));

		expect(screen.getByText('Email is required')).toBeInTheDocument();
	});
});
