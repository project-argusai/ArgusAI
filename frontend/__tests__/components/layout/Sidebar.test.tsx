/**
 * Sidebar Component Tests
 *
 * Tests for the desktop sidebar navigation with collapse functionality.
 *
 * Demonstrates:
 * - Testing navigation links with active states
 * - Testing collapse/expand functionality
 * - Testing localStorage persistence
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Sidebar } from '@/components/layout/Sidebar'
import React from 'react'

// Mock next/navigation
const mockPush = vi.fn()
vi.mock('next/navigation', () => ({
  usePathname: vi.fn(() => '/'),
  useRouter: () => ({
    push: mockPush,
  }),
}))

// Mock the AuthContext
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn(() => ({
    user: null,
    isAuthenticated: false,
    logout: vi.fn(),
  })),
}))

// Mock the SettingsContext
vi.mock('@/contexts/SettingsContext', () => ({
  useSettings: vi.fn(() => ({
    settings: {
      systemName: 'ArgusAI',
      aiProvider: 'openai',
      dataRetentionDays: 30,
      defaultMotionSensitivity: 'medium',
      theme: 'system',
      timezone: 'America/Chicago',
      backendUrl: 'http://localhost:8000',
    },
    isLoading: false,
    updateSetting: vi.fn(),
    updateSettings: vi.fn(),
    resetSettings: vi.fn(),
    refreshSystemName: vi.fn(),
  })),
}))

// Mock the NotificationContext
vi.mock('@/contexts/NotificationContext', () => ({
  useNotifications: vi.fn(() => ({
    notifications: [],
    unreadCount: 0,
    isLoading: false,
    fetchNotifications: vi.fn(),
    markAsRead: vi.fn(),
    markAllAsRead: vi.fn(),
    deleteNotification: vi.fn(),
    deleteAllNotifications: vi.fn(),
    connectionStatus: 'connected',
  })),
}))

// Mock the NotificationBell component
vi.mock('@/components/notifications/NotificationBell', () => ({
  NotificationBell: () => <button data-testid="notification-bell">Notifications</button>,
}))

// Import to mock pathname dynamically
import { usePathname } from 'next/navigation'
const mockUsePathname = usePathname as ReturnType<typeof vi.fn>

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value
    }),
    clear: vi.fn(() => {
      store = {}
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key]
    }),
  }
})()

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
})

describe('Sidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorageMock.clear()
    mockUsePathname.mockReturnValue('/')
  })

  describe('rendering', () => {
    it('renders all navigation links', () => {
      render(<Sidebar />)

      expect(screen.getByRole('link', { name: /dashboard/i })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: /events/i })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: /cameras/i })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: /rules/i })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: /settings/i })).toBeInTheDocument()
    })

    it('renders collapse button', () => {
      render(<Sidebar />)

      expect(screen.getByRole('button', { name: /collapse/i })).toBeInTheDocument()
    })
  })

  describe('navigation links', () => {
    it('Dashboard links to /', () => {
      render(<Sidebar />)

      const dashboardLink = screen.getByRole('link', { name: /dashboard/i })
      expect(dashboardLink).toHaveAttribute('href', '/')
    })

    it('Events links to /events', () => {
      render(<Sidebar />)

      const eventsLink = screen.getByRole('link', { name: /events/i })
      expect(eventsLink).toHaveAttribute('href', '/events')
    })

    it('Cameras links to /cameras', () => {
      render(<Sidebar />)

      const camerasLink = screen.getByRole('link', { name: /cameras/i })
      expect(camerasLink).toHaveAttribute('href', '/cameras')
    })

    it('Rules links to /rules', () => {
      render(<Sidebar />)

      const rulesLink = screen.getByRole('link', { name: /rules/i })
      expect(rulesLink).toHaveAttribute('href', '/rules')
    })

    it('Settings links to /settings', () => {
      render(<Sidebar />)

      const settingsLink = screen.getByRole('link', { name: /settings/i })
      expect(settingsLink).toHaveAttribute('href', '/settings')
    })
  })

  describe('active state', () => {
    it('highlights Dashboard when on home page', () => {
      mockUsePathname.mockReturnValue('/')
      const { container } = render(<Sidebar />)

      // Dashboard link should have active styling (bg-blue-600)
      const dashboardLink = screen.getByRole('link', { name: /dashboard/i })
      expect(dashboardLink).toHaveClass('bg-blue-600')
    })

    it('highlights Events when on /events', () => {
      mockUsePathname.mockReturnValue('/events')
      render(<Sidebar />)

      const eventsLink = screen.getByRole('link', { name: /events/i })
      expect(eventsLink).toHaveClass('bg-blue-600')
    })

    it('highlights Events when on /events/123 (subpage)', () => {
      mockUsePathname.mockReturnValue('/events/123')
      render(<Sidebar />)

      const eventsLink = screen.getByRole('link', { name: /events/i })
      expect(eventsLink).toHaveClass('bg-blue-600')
    })

    it('highlights Cameras when on /cameras', () => {
      mockUsePathname.mockReturnValue('/cameras')
      render(<Sidebar />)

      const camerasLink = screen.getByRole('link', { name: /cameras/i })
      expect(camerasLink).toHaveClass('bg-blue-600')
    })

    it('highlights Settings when on /settings', () => {
      mockUsePathname.mockReturnValue('/settings')
      render(<Sidebar />)

      const settingsLink = screen.getByRole('link', { name: /settings/i })
      expect(settingsLink).toHaveClass('bg-blue-600')
    })

    it('does not highlight Dashboard when on /events', () => {
      mockUsePathname.mockReturnValue('/events')
      render(<Sidebar />)

      const dashboardLink = screen.getByRole('link', { name: /dashboard/i })
      expect(dashboardLink).not.toHaveClass('bg-blue-600')
    })
  })

  describe('collapse functionality', () => {
    it('starts expanded by default', () => {
      const { container } = render(<Sidebar />)

      // Should show nav item text
      expect(screen.getByText('Dashboard')).toBeInTheDocument()

      // Sidebar should have expanded width class (w-60)
      const aside = container.querySelector('aside')
      expect(aside).toHaveClass('w-60')
    })

    it('collapses when collapse button clicked', async () => {
      const user = userEvent.setup()
      const { container } = render(<Sidebar />)

      await user.click(screen.getByRole('button', { name: /collapse/i }))

      // Sidebar should have collapsed width (w-16)
      const aside = container.querySelector('aside')
      expect(aside).toHaveClass('w-16')
    })

    it('hides text labels when collapsed', async () => {
      const user = userEvent.setup()
      render(<Sidebar />)

      await user.click(screen.getByRole('button', { name: /collapse/i }))

      // Text should be hidden
      expect(screen.queryByText('Dashboard')).not.toBeInTheDocument()
      expect(screen.queryByText('Events')).not.toBeInTheDocument()
    })

    it('expands when expand button clicked after collapsing', async () => {
      const user = userEvent.setup()
      const { container } = render(<Sidebar />)

      // Collapse
      await user.click(screen.getByRole('button', { name: /collapse/i }))

      // Expand (button now has expand title)
      await user.click(screen.getByRole('button', { name: /expand/i }))

      // Should be expanded again
      const aside = container.querySelector('aside')
      expect(aside).toHaveClass('w-60')
      expect(screen.getByText('Dashboard')).toBeInTheDocument()
    })

    it('shows title attribute on links when collapsed', async () => {
      const user = userEvent.setup()
      render(<Sidebar />)

      await user.click(screen.getByRole('button', { name: /collapse/i }))

      // Links should have title for accessibility
      const links = screen.getAllByRole('link')
      links.forEach(link => {
        expect(link).toHaveAttribute('title')
      })
    })

    it('does not show title attribute on links when expanded', () => {
      render(<Sidebar />)

      // Links should not have title when expanded (text is visible)
      const dashboardLink = screen.getByRole('link', { name: /dashboard/i })
      expect(dashboardLink).not.toHaveAttribute('title')
    })
  })

  describe('localStorage persistence', () => {
    it('saves collapsed state to localStorage', async () => {
      const user = userEvent.setup()
      render(<Sidebar />)

      await user.click(screen.getByRole('button', { name: /collapse/i }))

      expect(localStorageMock.setItem).toHaveBeenCalledWith('sidebar-collapsed', 'true')
    })

    it('saves expanded state to localStorage', async () => {
      const user = userEvent.setup()
      localStorageMock.getItem.mockReturnValue('true') // Start collapsed
      render(<Sidebar />)

      await user.click(screen.getByRole('button', { name: /expand/i }))

      expect(localStorageMock.setItem).toHaveBeenCalledWith('sidebar-collapsed', 'false')
    })

    it('loads collapsed state from localStorage on mount', () => {
      localStorageMock.getItem.mockReturnValue('true')
      const { container } = render(<Sidebar />)

      // Should start collapsed
      const aside = container.querySelector('aside')
      expect(aside).toHaveClass('w-16')
    })

    it('loads expanded state from localStorage on mount', () => {
      localStorageMock.getItem.mockReturnValue('false')
      const { container } = render(<Sidebar />)

      // Should start expanded
      const aside = container.querySelector('aside')
      expect(aside).toHaveClass('w-60')
    })

    it('defaults to expanded when localStorage is empty', () => {
      localStorageMock.getItem.mockReturnValue(null)
      const { container } = render(<Sidebar />)

      const aside = container.querySelector('aside')
      expect(aside).toHaveClass('w-60')
    })
  })

  describe('button states', () => {
    it('shows ChevronLeft icon when expanded', () => {
      const { container } = render(<Sidebar />)

      const chevronLeft = container.querySelector('.lucide-chevron-left')
      expect(chevronLeft).toBeInTheDocument()
    })

    it('shows ChevronRight icon when collapsed', async () => {
      const user = userEvent.setup()
      const { container } = render(<Sidebar />)

      await user.click(screen.getByRole('button', { name: /collapse/i }))

      const chevronRight = container.querySelector('.lucide-chevron-right')
      expect(chevronRight).toBeInTheDocument()
    })

    it('shows "Collapse" text when expanded', () => {
      render(<Sidebar />)

      expect(screen.getByText('Collapse')).toBeInTheDocument()
    })

    it('does not show "Collapse" text when collapsed', async () => {
      const user = userEvent.setup()
      render(<Sidebar />)

      await user.click(screen.getByRole('button', { name: /collapse/i }))

      expect(screen.queryByText('Collapse')).not.toBeInTheDocument()
    })
  })
})
