import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import MessageInput from '../src/components/MessageInput.svelte';

describe('MessageInput', () => {
	afterEach(cleanup);

	it('shows placeholder when disabled', () => {
		render(MessageInput, {
			props: { isStreaming: false, disabled: true, onSend: vi.fn(), onInterrupt: vi.fn() }
		});
		expect(screen.getByPlaceholderText('Select or create a conversation')).toBeInTheDocument();
	});

	it('shows send placeholder when enabled', () => {
		render(MessageInput, {
			props: { isStreaming: false, disabled: false, onSend: vi.fn(), onInterrupt: vi.fn() }
		});
		expect(screen.getByPlaceholderText('Send a message...')).toBeInTheDocument();
	});

	it('shows Send button when not streaming', () => {
		render(MessageInput, {
			props: { isStreaming: false, disabled: false, onSend: vi.fn(), onInterrupt: vi.fn() }
		});
		expect(screen.getByText('Send')).toBeInTheDocument();
	});

	it('shows Stop button when streaming', () => {
		render(MessageInput, {
			props: { isStreaming: true, disabled: false, onSend: vi.fn(), onInterrupt: vi.fn() }
		});
		expect(screen.getByText('Stop')).toBeInTheDocument();
	});

	it('calls onSend with trimmed text on Send click', async () => {
		const user = userEvent.setup();
		const onSend = vi.fn();
		render(MessageInput, {
			props: { isStreaming: false, disabled: false, onSend, onInterrupt: vi.fn() }
		});

		await user.type(screen.getByRole('textbox'), '  hello world  ');
		await user.click(screen.getByText('Send'));
		expect(onSend).toHaveBeenCalledWith('hello world');
	});

	it('clears input after sending', async () => {
		const user = userEvent.setup();
		render(MessageInput, {
			props: { isStreaming: false, disabled: false, onSend: vi.fn(), onInterrupt: vi.fn() }
		});

		const textarea = screen.getByRole('textbox');
		await user.type(textarea, 'hello');
		await user.click(screen.getByText('Send'));
		expect(textarea).toHaveValue('');
	});

	it('does not send whitespace-only input', async () => {
		const user = userEvent.setup();
		const onSend = vi.fn();
		render(MessageInput, {
			props: { isStreaming: false, disabled: false, onSend, onInterrupt: vi.fn() }
		});

		await user.type(screen.getByRole('textbox'), '   ');
		await user.click(screen.getByText('Send'));
		expect(onSend).not.toHaveBeenCalled();
	});

	it('calls onInterrupt when Stop clicked', async () => {
		const user = userEvent.setup();
		const onInterrupt = vi.fn();
		render(MessageInput, {
			props: { isStreaming: true, disabled: false, onSend: vi.fn(), onInterrupt }
		});

		await user.click(screen.getByText('Stop'));
		expect(onInterrupt).toHaveBeenCalledOnce();
	});

	it('disables textarea when disabled prop is true', () => {
		render(MessageInput, {
			props: { isStreaming: false, disabled: true, onSend: vi.fn(), onInterrupt: vi.fn() }
		});
		expect(screen.getByRole('textbox')).toBeDisabled();
	});

	it('disables textarea when streaming', () => {
		render(MessageInput, {
			props: { isStreaming: true, disabled: false, onSend: vi.fn(), onInterrupt: vi.fn() }
		});
		expect(screen.getByRole('textbox')).toBeDisabled();
	});
});
