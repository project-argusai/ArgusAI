/**
 * Header Component Tests
 *
 * Tests for the application header with navigation and user menu.
 *
 * Demonstrates:
 * - Testing navigation links
 * - Testing authentication context
 * - Testing mobile menu toggle
 * - Testing user dropdown menu
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Header } from '@/components/layout/Header'
import { useAuth } from '@/contexts/AuthContext'
import { TooltipProvider } from '@/components/ui/tooltip'
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
  useAuth: vi.fn(),
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

// Mock the NotificationBell to simplify testing
vi.mock('@/components/notifications', () => ({
  NotificationBell: () => <button data-testid="notification-bell">Notifications</button>,
}))

// Mock sonner toast
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

const mockUseAuth = useAuth as ReturnType<typeof vi.fn>

// Wrapper with TooltipProvider
function TestWrapper({ children }: { children: React.ReactNode }) {
  return <TooltipProvider>{children}</TooltipProvider>
}

describe('Header', () => {
  const mockLogout = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    mockLogout.mockResolvedValue(undefined)
  })

  describe('rendering', () => {
    it('renders logo and app name', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        logout: mockLogout,
      })

      render(<Header />, { wrapper: TestWrapper })

      expect(screen.getByText('ArgusAI')).toBeInTheDocument()
    })

    it('renders navigation links', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        logout: mockLogout,
      })

      render(<Header />, { wrapper: TestWrapper })

      expect(screen.getByRole('link', { name: /dashboard/i })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: /events/i })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: /cameras/i })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: /rules/i })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: /settings/i })).toBeInTheDocument()
    })

    it('renders notification bell', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        logout: mockLogout,
      })

      render(<Header />, { wrapper: TestWrapper })

      expect(screen.getByTestId('notification-bell')).toBeInTheDocument()
    })

    it('renders system status indicator', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        logout: mockLogout,
      })

      render(<Header />, { wrapper: TestWrapper })

      expect(screen.getByText('Healthy')).toBeInTheDocument()
    })
  })

  describe('navigation links', () => {
    it('has correct href for Dashboard', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        logout: mockLogout,
      })

      render(<Header />, { wrapper: TestWrapper })

      const dashboardLink = screen.getByRole('link', { name: /dashboard/i })
      expect(dashboardLink).toHaveAttribute('href', '/')
    })

    it('has correct href for Events', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        logout: mockLogout,
      })

      render(<Header />, { wrapper: TestWrapper })

      const eventsLink = screen.getByRole('link', { name: /events/i })
      expect(eventsLink).toHaveAttribute('href', '/events')
    })

    it('has correct href for Cameras', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        logout: mockLogout,
      })

      render(<Header />, { wrapper: TestWrapper })

      const camerasLink = screen.getByRole('link', { name: /cameras/i })
      expect(camerasLink).toHaveAttribute('href', '/cameras')
    })

    it('has correct href for Rules', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        logout: mockLogout,
      })

      render(<Header />, { wrapper: TestWrapper })

      const rulesLink = screen.getByRole('link', { name: /rules/i })
      expect(rulesLink).toHaveAttribute('href', '/rules')
    })

    it('has correct href for Settings', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        logout: mockLogout,
      })

      render(<Header />, { wrapper: TestWrapper })

      const settingsLink = screen.getByRole('link', { name: /settings/i })
      expect(settingsLink).toHaveAttribute('href', '/settings')
    })
  })

  describe('user authentication', () => {
    it('shows user menu when authenticated', () => {
      mockUseAuth.mockReturnValue({
        user: { username: 'testuser' },
        isAuthenticated: true,
        logout: mockLogout,
      })

      const { container } = render(<Header />, { wrapper: TestWrapper })

      // User icon button should be present
      const userButtons = container.querySelectorAll('button')
      const userButton = Array.from(userButtons).find(btn =>
        btn.querySelector('.lucide-user')
      )
      expect(userButton).toBeTruthy()
    })

    it('does not show user menu when not authenticated', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        logout: mockLogout,
      })

      const { container } = render(<Header />, { wrapper: TestWrapper })

      // User icon should not be present - it's hidden on mobile and shown on md,
      // but not present in dropdown context if not authenticated
      const dropdownTriggers = container.querySelectorAll('[data-slot="dropdown-menu-trigger"]')
      expect(dropdownTriggers.length).toBe(0)
    })

    it('opens user dropdown when clicked', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({
        user: { username: 'testuser' },
        isAuthenticated: true,
        logout: mockLogout,
      })

      const { container } = render(<Header />, { wrapper: TestWrapper })

      // Find the user button (has User icon)
      const userButton = container.querySelector('button:has(.lucide-user)')
      expect(userButton).toBeTruthy()

      await user.click(userButton!)

      await waitFor(() => {
        expect(screen.getByText('testuser')).toBeInTheDocument()
      })
    })

    it('shows logout option in dropdown', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({
        user: { username: 'testuser' },
        isAuthenticated: true,
        logout: mockLogout,
      })

      const { container } = render(<Header />, { wrapper: TestWrapper })

      const userButton = container.querySelector('button:has(.lucide-user)')
      await user.click(userButton!)

      await waitFor(() => {
        expect(screen.getByText('Logout')).toBeInTheDocument()
      })
    })

    it('calls logout and redirects when logout clicked', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({
        user: { username: 'testuser' },
        isAuthenticated: true,
        logout: mockLogout,
      })

      const { container } = render(<Header />, { wrapper: TestWrapper })

      const userButton = container.querySelector('button:has(.lucide-user)')
      await user.click(userButton!)

      await waitFor(() => {
        expect(screen.getByText('Logout')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Logout'))

      await waitFor(() => {
        expect(mockLogout).toHaveBeenCalled()
      })
      expect(mockPush).toHaveBeenCalledWith('/login')
    })

    it('shows settings link in user dropdown', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({
        user: { username: 'testuser' },
        isAuthenticated: true,
        logout: mockLogout,
      })

      const { container } = render(<Header />, { wrapper: TestWrapper })

      const userButton = container.querySelector('button:has(.lucide-user)')
      await user.click(userButton!)

      await waitFor(() => {
        // Should have Settings link in dropdown
        const settingsLinks = screen.getAllByText('Settings')
        expect(settingsLinks.length).toBeGreaterThanOrEqual(1)
      })
    })

    it('shows change password link in user dropdown', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({
        user: { username: 'testuser' },
        isAuthenticated: true,
        logout: mockLogout,
      })

      const { container } = render(<Header />, { wrapper: TestWrapper })

      const userButton = container.querySelector('button:has(.lucide-user)')
      await user.click(userButton!)

      await waitFor(() => {
        expect(screen.getByText('Change Password')).toBeInTheDocument()
      })
    })
  })

  describe('mobile menu', () => {
    it('toggles mobile menu when button clicked', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        logout: mockLogout,
      })

      const { container } = render(<Header />, { wrapper: TestWrapper })

      // Find mobile menu button (has Menu icon and md:hidden class)
      const mobileButton = container.querySelector('button:has(.lucide-menu)')
      expect(mobileButton).toBeTruthy()

      await user.click(mobileButton!)

      // Mobile nav should now be visible (there will be duplicate nav links)
      const dashboardLinks = screen.getAllByText('Dashboard')
      expect(dashboardLinks.length).toBe(2) // Desktop + mobile
    })

    it('closes mobile menu when nav item clicked', async () => {
      const user = userEvent.setup()
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        logout: mockLogout,
      })

      const { container } = render(<Header />, { wrapper: TestWrapper })

      // Open mobile menu
      const mobileButton = container.querySelector('button:has(.lucide-menu)')
      await user.click(mobileButton!)

      // Get mobile nav links (the mobile ones are in a separate nav)
      const allLinks = screen.getAllByRole('link', { name: /events/i })
      const mobileLink = allLinks[allLinks.length - 1] // Last one is mobile

      await user.click(mobileLink)

      // Mobile menu should close (back to 1 instance of each link)
      await waitFor(() => {
        const dashboardLinks = screen.getAllByText('Dashboard')
        expect(dashboardLinks.length).toBe(1)
      })
    })
  })

  describe('logo link', () => {
    it('logo links to home page', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        logout: mockLogout,
      })

      render(<Header />, { wrapper: TestWrapper })

      // The logo link contains the system name from SettingsContext (mocked as 'ArgusAI')
      const logoLink = screen.getByRole('link', { name: /argusai/i })
      expect(logoLink).toHaveAttribute('href', '/')
    })
  })
})
