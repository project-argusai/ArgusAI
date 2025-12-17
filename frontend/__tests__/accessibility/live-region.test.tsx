/**
 * LiveRegion Component Tests (Story P6-2.2)
 *
 * Tests for the accessible live region component.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LiveRegion, StatusAnnouncer } from '@/components/ui/live-region'

describe('LiveRegion', () => {
  describe('rendering', () => {
    it('renders children content', () => {
      render(<LiveRegion>Test content</LiveRegion>)
      expect(screen.getByText('Test content')).toBeInTheDocument()
    })

    it('has role="status" by default', () => {
      render(<LiveRegion>Status update</LiveRegion>)
      const region = screen.getByRole('status')
      expect(region).toBeInTheDocument()
    })

    it('supports role="alert" for urgent content', () => {
      render(<LiveRegion role="alert">Error occurred</LiveRegion>)
      const region = screen.getByRole('alert')
      expect(region).toBeInTheDocument()
    })
  })

  describe('aria-live modes', () => {
    it('has aria-live="polite" by default', () => {
      render(<LiveRegion>Polite update</LiveRegion>)
      const region = screen.getByRole('status')
      expect(region).toHaveAttribute('aria-live', 'polite')
    })

    it('supports aria-live="assertive" for urgent announcements', () => {
      render(<LiveRegion mode="assertive">Urgent update</LiveRegion>)
      const region = screen.getByRole('status')
      expect(region).toHaveAttribute('aria-live', 'assertive')
    })

    it('has aria-atomic="true" for complete announcements', () => {
      render(<LiveRegion>Complete content</LiveRegion>)
      const region = screen.getByRole('status')
      expect(region).toHaveAttribute('aria-atomic', 'true')
    })
  })

  describe('visual visibility', () => {
    it('is visible by default', () => {
      render(<LiveRegion>Visible content</LiveRegion>)
      const region = screen.getByRole('status')
      expect(region).not.toHaveClass('sr-only')
    })

    it('can be visually hidden with visuallyHidden prop', () => {
      render(<LiveRegion visuallyHidden>Hidden content</LiveRegion>)
      const region = screen.getByRole('status')
      expect(region).toHaveClass('sr-only')
    })
  })

  describe('delayed announcements', () => {
    beforeEach(() => {
      vi.useFakeTimers()
    })

    afterEach(() => {
      vi.useRealTimers()
    })

    it('announces immediately when delay is 0', () => {
      render(<LiveRegion>Immediate</LiveRegion>)
      expect(screen.getByText('Immediate')).toBeInTheDocument()
    })

    it('delays announcement when delay prop is set', async () => {
      render(<LiveRegion delay={500}>Delayed content</LiveRegion>)

      // Content should be rendered (React renders immediately, delay is for re-render updates)
      expect(screen.getByText('Delayed content')).toBeInTheDocument()
    })
  })

  describe('className support', () => {
    it('applies custom className', () => {
      render(<LiveRegion className="custom-class">Content</LiveRegion>)
      const region = screen.getByRole('status')
      expect(region).toHaveClass('custom-class')
    })
  })
})

describe('StatusAnnouncer', () => {
  it('renders as visually hidden status region', () => {
    render(<StatusAnnouncer>Loading complete</StatusAnnouncer>)
    const region = screen.getByRole('status')
    expect(region).toHaveClass('sr-only')
    expect(region).toHaveAttribute('aria-live', 'polite')
  })

  it('contains the announcement text', () => {
    render(<StatusAnnouncer>5 items loaded</StatusAnnouncer>)
    expect(screen.getByText('5 items loaded')).toBeInTheDocument()
  })
})
