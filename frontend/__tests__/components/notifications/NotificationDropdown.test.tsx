/**
 * NotificationDropdown Component Tests
 *
 * Tests for the notification dropdown panel with real-time notifications.
 *
 * Demonstrates:
 * - Testing components with context providers
 * - Testing notification list rendering
 * - Testing read/unread states
 * - Testing navigation actions
 * - Testing delete functionality
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { NotificationDropdown } from '@/components/notifications/NotificationDropdown'
import { useNotifications } from '@/contexts/NotificationContext'
import type { INotification } from '@/types/notification'

// Mock the NotificationContext
vi.mock('@/contexts/NotificationContext', () => ({
  useNotifications: vi.fn(),
}))

// Mock next/navigation
const mockPush = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}))

const mockUseNotifications = useNotifications as ReturnType<typeof vi.fn>

// Helper to create mock notifications
const createMockNotification = (overrides?: Partial<INotification>): INotification => ({
  id: 'notif-123',
  event_id: 'evt-456',
  rule_id: 'rule-789',
  rule_name: 'Motion Alert',
  event_description: 'Person detected at front door',
  thumbnail_url: '/api/v1/thumbnails/notif-123.jpg',
  read: false,
  created_at: new Date().toISOString(),
  is_doorbell_ring: false,
  ...overrides,
})

describe('NotificationDropdown', () => {
  const mockMarkAsRead = vi.fn()
  const mockMarkAllAsRead = vi.fn()
  const mockDeleteNotification = vi.fn()
  const mockOnClose = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    mockMarkAsRead.mockResolvedValue(undefined)
    mockMarkAllAsRead.mockResolvedValue(undefined)
    mockDeleteNotification.mockResolvedValue(undefined)
  })

  describe('loading state', () => {
    it('shows loading spinner when isLoading is true', () => {
      mockUseNotifications.mockReturnValue({
        notifications: [],
        unreadCount: 0,
        isLoading: true,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      const { container } = render(<NotificationDropdown />)

      // Should show loading spinner (svg with animate-spin class)
      const spinner = container.querySelector('.animate-spin')
      expect(spinner).toBeInTheDocument()
    })
  })

  describe('empty state', () => {
    it('shows empty message when no notifications', () => {
      mockUseNotifications.mockReturnValue({
        notifications: [],
        unreadCount: 0,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      render(<NotificationDropdown />)

      expect(screen.getByText('No notifications yet')).toBeInTheDocument()
      expect(screen.getByText(/You'll see alerts here when rules trigger/i)).toBeInTheDocument()
    })

    it('does not show mark all as read button when no notifications', () => {
      mockUseNotifications.mockReturnValue({
        notifications: [],
        unreadCount: 0,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      render(<NotificationDropdown />)

      expect(screen.queryByText(/mark all as read/i)).not.toBeInTheDocument()
    })

    it('does not show view all events link when no notifications', () => {
      mockUseNotifications.mockReturnValue({
        notifications: [],
        unreadCount: 0,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      render(<NotificationDropdown />)

      expect(screen.queryByText(/view all events/i)).not.toBeInTheDocument()
    })
  })

  describe('notification list', () => {
    it('renders notifications list', () => {
      const notifications = [
        createMockNotification({ id: 'notif-1', rule_name: 'Motion Alert' }),
        createMockNotification({ id: 'notif-2', rule_name: 'Person Detected' }),
      ]

      mockUseNotifications.mockReturnValue({
        notifications,
        unreadCount: 2,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      render(<NotificationDropdown />)

      expect(screen.getByText('Motion Alert')).toBeInTheDocument()
      expect(screen.getByText('Person Detected')).toBeInTheDocument()
    })

    it('shows Notifications header', () => {
      mockUseNotifications.mockReturnValue({
        notifications: [createMockNotification()],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      render(<NotificationDropdown />)

      expect(screen.getByText('Notifications')).toBeInTheDocument()
    })

    it('shows event description', () => {
      mockUseNotifications.mockReturnValue({
        notifications: [
          createMockNotification({ event_description: 'Person walking towards door' }),
        ],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      render(<NotificationDropdown />)

      expect(screen.getByText('Person walking towards door')).toBeInTheDocument()
    })

    it('shows view all events link when notifications exist', () => {
      mockUseNotifications.mockReturnValue({
        notifications: [createMockNotification()],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      render(<NotificationDropdown />)

      expect(screen.getByText(/view all events/i)).toBeInTheDocument()
    })
  })

  describe('read/unread state', () => {
    it('shows mark all as read button when unread notifications exist', () => {
      mockUseNotifications.mockReturnValue({
        notifications: [createMockNotification({ read: false })],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      render(<NotificationDropdown />)

      expect(screen.getByText(/mark all as read/i)).toBeInTheDocument()
    })

    it('does not show mark all as read when all are read', () => {
      mockUseNotifications.mockReturnValue({
        notifications: [createMockNotification({ read: true })],
        unreadCount: 0,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      render(<NotificationDropdown />)

      expect(screen.queryByText(/mark all as read/i)).not.toBeInTheDocument()
    })

    it('calls markAllAsRead when button is clicked', async () => {
      const user = userEvent.setup()

      mockUseNotifications.mockReturnValue({
        notifications: [createMockNotification({ read: false })],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      render(<NotificationDropdown />)

      await user.click(screen.getByText(/mark all as read/i))

      expect(mockMarkAllAsRead).toHaveBeenCalled()
    })
  })

  describe('notification click', () => {
    it('marks notification as read and navigates to event', async () => {
      const user = userEvent.setup()
      const notification = createMockNotification({
        id: 'notif-123',
        event_id: 'evt-456',
        read: false,
      })

      mockUseNotifications.mockReturnValue({
        notifications: [notification],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      render(<NotificationDropdown onClose={mockOnClose} />)

      await user.click(screen.getByText('Motion Alert'))

      await waitFor(() => {
        expect(mockMarkAsRead).toHaveBeenCalledWith('notif-123')
      })
      expect(mockPush).toHaveBeenCalledWith('/events?event=evt-456')
      expect(mockOnClose).toHaveBeenCalled()
    })

    it('does not call markAsRead if already read', async () => {
      const user = userEvent.setup()
      const notification = createMockNotification({
        id: 'notif-123',
        event_id: 'evt-456',
        read: true,
      })

      mockUseNotifications.mockReturnValue({
        notifications: [notification],
        unreadCount: 0,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      render(<NotificationDropdown onClose={mockOnClose} />)

      await user.click(screen.getByText('Motion Alert'))

      expect(mockMarkAsRead).not.toHaveBeenCalled()
      expect(mockPush).toHaveBeenCalledWith('/events?event=evt-456')
    })
  })

  describe('delete notification', () => {
    it('calls deleteNotification when delete button clicked', async () => {
      const user = userEvent.setup()

      mockUseNotifications.mockReturnValue({
        notifications: [createMockNotification({ id: 'notif-to-delete' })],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      render(<NotificationDropdown />)

      // Find delete button (trash icon button)
      const deleteButton = screen.getByRole('button', { name: '' })
      await user.click(deleteButton)

      expect(mockDeleteNotification).toHaveBeenCalledWith('notif-to-delete')
    })

    it('does not navigate when delete button clicked', async () => {
      const user = userEvent.setup()

      mockUseNotifications.mockReturnValue({
        notifications: [createMockNotification()],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      render(<NotificationDropdown onClose={mockOnClose} />)

      const deleteButton = screen.getByRole('button', { name: '' })
      await user.click(deleteButton)

      // Should not navigate
      expect(mockPush).not.toHaveBeenCalled()
      expect(mockOnClose).not.toHaveBeenCalled()
    })
  })

  describe('doorbell notifications', () => {
    it('displays doorbell ring with special styling', () => {
      mockUseNotifications.mockReturnValue({
        notifications: [
          createMockNotification({
            is_doorbell_ring: true,
            rule_name: 'Doorbell',
          }),
        ],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      render(<NotificationDropdown />)

      // Doorbell ring should show "Doorbell Ring" title instead of rule_name
      expect(screen.getByText('Doorbell Ring')).toBeInTheDocument()
    })

    it('shows doorbell icon for doorbell notifications', () => {
      mockUseNotifications.mockReturnValue({
        notifications: [
          createMockNotification({
            is_doorbell_ring: true,
          }),
        ],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      render(<NotificationDropdown />)

      // Should have doorbell icon (aria-label)
      expect(screen.getByLabelText('Doorbell ring')).toBeInTheDocument()
    })

    it('sorts doorbell notifications to top', () => {
      const notifications = [
        createMockNotification({
          id: 'notif-1',
          rule_name: 'Motion Alert',
          is_doorbell_ring: false,
          created_at: new Date('2024-01-15T10:00:00Z').toISOString(),
        }),
        createMockNotification({
          id: 'notif-2',
          rule_name: 'Doorbell',
          is_doorbell_ring: true,
          created_at: new Date('2024-01-15T09:00:00Z').toISOString(), // Earlier time
        }),
      ]

      mockUseNotifications.mockReturnValue({
        notifications,
        unreadCount: 2,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      render(<NotificationDropdown />)

      // Doorbell Ring should appear first despite being created earlier
      const items = screen.getAllByText(/Doorbell Ring|Motion Alert/)
      expect(items[0]).toHaveTextContent('Doorbell Ring')
      expect(items[1]).toHaveTextContent('Motion Alert')
    })
  })

  describe('view all events', () => {
    it('navigates to events page with filter when view all clicked', async () => {
      const user = userEvent.setup()

      mockUseNotifications.mockReturnValue({
        notifications: [createMockNotification()],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      render(<NotificationDropdown onClose={mockOnClose} />)

      await user.click(screen.getByText(/view all events/i))

      expect(mockPush).toHaveBeenCalledWith('/events?filter=alerts')
      expect(mockOnClose).toHaveBeenCalled()
    })
  })

  describe('thumbnail', () => {
    it('renders thumbnail image when thumbnail_url exists', () => {
      mockUseNotifications.mockReturnValue({
        notifications: [
          createMockNotification({
            thumbnail_url: '/api/v1/thumbnails/test.jpg',
          }),
        ],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      const { container } = render(<NotificationDropdown />)

      // Image has alt="" so we need to query by tag
      const img = container.querySelector('img')
      expect(img).toBeInTheDocument()
      expect(img).toHaveAttribute('src', expect.stringContaining('/api/v1/thumbnails/test.jpg'))
    })

    it('shows "No image" placeholder when thumbnail_url is null', () => {
      mockUseNotifications.mockReturnValue({
        notifications: [
          createMockNotification({
            thumbnail_url: null,
            is_doorbell_ring: false,
          }),
        ],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      render(<NotificationDropdown />)

      expect(screen.getByText('No image')).toBeInTheDocument()
    })
  })

  describe('timestamp', () => {
    it('shows relative timestamp', () => {
      // Set notification created 5 minutes ago
      const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString()

      mockUseNotifications.mockReturnValue({
        notifications: [
          createMockNotification({
            created_at: fiveMinutesAgo,
          }),
        ],
        unreadCount: 1,
        isLoading: false,
        markAsRead: mockMarkAsRead,
        markAllAsRead: mockMarkAllAsRead,
        deleteNotification: mockDeleteNotification,
      })

      render(<NotificationDropdown />)

      // Should show something like "5 minutes ago" or "less than a minute ago"
      expect(screen.getByText(/ago/i)).toBeInTheDocument()
    })
  })
})
