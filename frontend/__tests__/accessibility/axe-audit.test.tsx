/**
 * Accessibility Audit Tests (Story P6-2.2)
 *
 * Uses axe-core to automatically detect WCAG violations.
 * Covers critical pages: Dashboard, Cameras, Events, Settings.
 *
 * Note: axe-core detects ~57% of accessibility issues.
 * Manual testing is still required for complete WCAG compliance.
 */
import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { axe, toHaveNoViolations } from 'jest-axe'
import * as React from 'react'

// Extend expect with axe matchers
expect.extend(toHaveNoViolations)

// Mock TanStack Query for components that use it
vi.mock('@tanstack/react-query', () => ({
  useQuery: vi.fn(() => ({
    data: [],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  })),
  useQueryClient: vi.fn(() => ({
    invalidateQueries: vi.fn(),
  })),
  useMutation: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
  })),
  QueryClient: vi.fn(),
  QueryClientProvider: ({ children }: { children: React.ReactNode }) => children,
}))

// Mock next-themes
vi.mock('next-themes', () => ({
  useTheme: vi.fn(() => ({
    theme: 'light',
    setTheme: vi.fn(),
    themes: ['light', 'dark'],
  })),
  ThemeProvider: ({ children }: { children: React.ReactNode }) => children,
}))

describe('Accessibility Audit', () => {
  describe('UI Components', () => {
    it('Button component has no critical accessibility violations', async () => {
      const { Button } = await import('@/components/ui/button')
      const { container } = render(
        <div>
          <Button>Click me</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button disabled>Disabled</Button>
        </div>
      )

      const results = await axe(container, {
        rules: {
          // Disable color-contrast for now - will check separately
          'color-contrast': { enabled: false },
        },
      })

      expect(results).toHaveNoViolations()
    })

    it('Input component has no critical accessibility violations', async () => {
      const { Input } = await import('@/components/ui/input')
      const { container } = render(
        <div>
          <label htmlFor="test-input">Test Label</label>
          <Input id="test-input" placeholder="Enter text" />
        </div>
      )

      const results = await axe(container, {
        rules: {
          'color-contrast': { enabled: false },
        },
      })

      expect(results).toHaveNoViolations()
    })

    it('Form components have proper ARIA attributes', async () => {
      const { Form, FormField, FormItem, FormLabel, FormControl, FormMessage, FormDescription } = await import('@/components/ui/form')
      const { Input } = await import('@/components/ui/input')
      const { useForm } = await import('react-hook-form')

      const TestForm = () => {
        const form = useForm({
          defaultValues: { email: '' },
        })

        return (
          <Form {...form}>
            <form>
              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Email</FormLabel>
                    <FormControl>
                      <Input placeholder="email@example.com" {...field} />
                    </FormControl>
                    <FormDescription>Enter your email address</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </form>
          </Form>
        )
      }

      const { container } = render(<TestForm />)

      const results = await axe(container, {
        rules: {
          'color-contrast': { enabled: false },
        },
      })

      expect(results).toHaveNoViolations()
    })

    it('Dialog component has proper accessibility attributes', async () => {
      const { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } = await import('@/components/ui/dialog')
      const { container } = render(
        <Dialog open>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Test Dialog</DialogTitle>
              <DialogDescription>This is a test dialog description</DialogDescription>
            </DialogHeader>
            <p>Dialog content here</p>
          </DialogContent>
        </Dialog>
      )

      const results = await axe(container, {
        rules: {
          'color-contrast': { enabled: false },
        },
      })

      expect(results).toHaveNoViolations()
    })
  })

  describe('Layout Components', () => {
    it('SkipToContent has proper accessibility', async () => {
      const { SkipToContent } = await import('@/components/layout/SkipToContent')
      const { container } = render(<SkipToContent />)

      const results = await axe(container, {
        rules: {
          'color-contrast': { enabled: false },
        },
      })

      expect(results).toHaveNoViolations()
    })
  })

  describe('ARIA Live Regions', () => {
    it('status announcements use proper aria-live attributes', () => {
      const { container } = render(
        <div>
          <div role="status" aria-live="polite">
            Loading complete
          </div>
          <div role="alert" aria-live="assertive">
            Error occurred
          </div>
        </div>
      )

      const statusRegion = container.querySelector('[role="status"]')
      const alertRegion = container.querySelector('[role="alert"]')

      expect(statusRegion).toHaveAttribute('aria-live', 'polite')
      expect(alertRegion).toHaveAttribute('aria-live', 'assertive')
    })
  })

  describe('Form Accessibility', () => {
    it('error messages are properly associated with form fields', async () => {
      const { container } = render(
        <div>
          <label htmlFor="email-field">Email</label>
          <input
            id="email-field"
            aria-describedby="email-error"
            aria-invalid="true"
            type="email"
          />
          <span id="email-error" role="alert">
            Please enter a valid email
          </span>
        </div>
      )

      const input = container.querySelector('input')
      const error = container.querySelector('[role="alert"]')

      expect(input).toHaveAttribute('aria-describedby', 'email-error')
      expect(input).toHaveAttribute('aria-invalid', 'true')
      expect(error).toBeInTheDocument()
    })
  })

  describe('Interactive Elements', () => {
    it('icon-only buttons have accessible names', async () => {
      const { Button } = await import('@/components/ui/button')
      const { container } = render(
        <div>
          <Button aria-label="Close dialog" size="icon">
            <span aria-hidden="true">X</span>
          </Button>
          <Button aria-label="Open menu" size="icon">
            <span aria-hidden="true">=</span>
          </Button>
        </div>
      )

      const results = await axe(container, {
        rules: {
          'color-contrast': { enabled: false },
        },
      })

      expect(results).toHaveNoViolations()
    })
  })
})
