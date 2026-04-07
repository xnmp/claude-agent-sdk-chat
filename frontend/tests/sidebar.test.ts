import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import Sidebar from '../src/components/Sidebar.svelte';
import type { Conversation, User } from '$lib/types';

const mockUser: User = { id: '1', email: 'test@example.com', display_name: 'Test User' };

function makeConversation(overrides: Partial<Conversation> = {}): Conversation {
	return {
		id: crypto.randomUUID(),
		title: null,
		sdk_session_id: null,
		created_at: new Date().toISOString(),
		updated_at: new Date().toISOString(),
		...overrides
	};
}

describe('Sidebar', () => {
	afterEach(cleanup);

	it('shows user display name', () => {
		render(Sidebar, {
			props: {
				conversations: [],
				activeConversationId: null,
				onSelect: vi.fn(),
				onNew: vi.fn(),
				onDelete: vi.fn(),
				user: mockUser,
				onLogout: vi.fn()
			}
		});
		expect(screen.getByText('Test User')).toBeInTheDocument();
	});

	it('shows empty state when no conversations', () => {
		render(Sidebar, {
			props: {
				conversations: [],
				activeConversationId: null,
				onSelect: vi.fn(),
				onNew: vi.fn(),
				onDelete: vi.fn(),
				user: mockUser,
				onLogout: vi.fn()
			}
		});
		expect(screen.getByText('No conversations yet')).toBeInTheDocument();
	});

	it('renders conversation titles', () => {
		const convs = [
			makeConversation({ title: 'First chat' }),
			makeConversation({ title: 'Second chat' })
		];
		render(Sidebar, {
			props: {
				conversations: convs,
				activeConversationId: null,
				onSelect: vi.fn(),
				onNew: vi.fn(),
				onDelete: vi.fn(),
				user: mockUser,
				onLogout: vi.fn()
			}
		});
		expect(screen.getByText('First chat')).toBeInTheDocument();
		expect(screen.getByText('Second chat')).toBeInTheDocument();
	});

	it('shows "New conversation" for untitled conversations', () => {
		render(Sidebar, {
			props: {
				conversations: [makeConversation({ title: null })],
				activeConversationId: null,
				onSelect: vi.fn(),
				onNew: vi.fn(),
				onDelete: vi.fn(),
				user: mockUser,
				onLogout: vi.fn()
			}
		});
		expect(screen.getByText('New conversation')).toBeInTheDocument();
	});

	it('calls onNew when + New button clicked', async () => {
		const user = userEvent.setup();
		const onNew = vi.fn();
		render(Sidebar, {
			props: {
				conversations: [],
				activeConversationId: null,
				onSelect: vi.fn(),
				onNew,
				onDelete: vi.fn(),
				user: mockUser,
				onLogout: vi.fn()
			}
		});

		await user.click(screen.getByText('New'));
		expect(onNew).toHaveBeenCalledOnce();
	});

	it('calls onLogout when Sign out clicked', async () => {
		const user = userEvent.setup();
		const onLogout = vi.fn();
		render(Sidebar, {
			props: {
				conversations: [],
				activeConversationId: null,
				onSelect: vi.fn(),
				onNew: vi.fn(),
				onDelete: vi.fn(),
				user: mockUser,
				onLogout
			}
		});

		await user.click(screen.getByText('Sign out'));
		expect(onLogout).toHaveBeenCalledOnce();
	});

	it('calls onSelect when conversation clicked', async () => {
		const user = userEvent.setup();
		const onSelect = vi.fn();
		const conv = makeConversation({ title: 'Click me' });
		render(Sidebar, {
			props: {
				conversations: [conv],
				activeConversationId: null,
				onSelect,
				onNew: vi.fn(),
				onDelete: vi.fn(),
				user: mockUser,
				onLogout: vi.fn()
			}
		});

		await user.click(screen.getByText('Click me'));
		expect(onSelect).toHaveBeenCalledWith(conv.id);
	});

	it('marks active conversation with active class', () => {
		const conv = makeConversation({ title: 'Active one' });
		const { container } = render(Sidebar, {
			props: {
				conversations: [conv],
				activeConversationId: conv.id,
				onSelect: vi.fn(),
				onNew: vi.fn(),
				onDelete: vi.fn(),
				user: mockUser,
				onLogout: vi.fn()
			}
		});

		const item = container.querySelector('.conversation-item');
		expect(item?.classList.contains('active')).toBe(true);
	});

	it('falls back to email when display_name is null', () => {
		const userNoName: User = { id: '2', email: 'fallback@example.com', display_name: null };
		render(Sidebar, {
			props: {
				conversations: [],
				activeConversationId: null,
				onSelect: vi.fn(),
				onNew: vi.fn(),
				onDelete: vi.fn(),
				user: userNoName,
				onLogout: vi.fn()
			}
		});
		expect(screen.getByText('fallback@example.com')).toBeInTheDocument();
	});
});
