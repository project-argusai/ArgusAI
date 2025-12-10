/**
 * Tests for ReanalyzedIndicator component
 *
 * Story P3-6.4 AC7: Shows "Re-analyzed" indicator for re-analyzed events
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '../../test-utils'
import { ReanalyzedIndicator } from '@/components/events/ReanalyzedIndicator'

describe('ReanalyzedIndicator', () => {
  // AC7: Test indicator shows for re-analyzed events
  describe('AC7: Show Re-Analysis History', () => {
    it('renders indicator when reanalyzed_at is present', () => {
      const reanalyzedAt = new Date().toISOString()

      render(<ReanalyzedIndicator reanalyzedAt={reanalyzedAt} />)

      expect(screen.getByText('Re-analyzed')).toBeInTheDocument()
    })

    it('does not render when reanalyzed_at is null', () => {
      render(<ReanalyzedIndicator reanalyzedAt={null} />)

      expect(screen.queryByText('Re-analyzed')).not.toBeInTheDocument()
    })

    it('does not render when reanalyzed_at is undefined', () => {
      render(<ReanalyzedIndicator reanalyzedAt={undefined} />)

      expect(screen.queryByText('Re-analyzed')).not.toBeInTheDocument()
    })
  })

  describe('Styling and Accessibility', () => {
    it('uses RefreshCw icon', () => {
      const reanalyzedAt = new Date().toISOString()

      render(<ReanalyzedIndicator reanalyzedAt={reanalyzedAt} />)

      // Find the parent span that wraps the icon and text
      const textSpan = screen.getByText('Re-analyzed')
      const container = textSpan.parentElement
      expect(container?.querySelector('svg')).toBeInTheDocument()
    })

    it('has screen reader text with relative time', () => {
      const reanalyzedAt = new Date().toISOString()

      render(<ReanalyzedIndicator reanalyzedAt={reanalyzedAt} />)

      // Should have sr-only text with relative time
      const srText = screen.getByText(/Re-analyzed.*ago/i, { selector: '.sr-only' })
      expect(srText).toBeInTheDocument()
    })

    it('is keyboard accessible', () => {
      const reanalyzedAt = new Date().toISOString()

      render(<ReanalyzedIndicator reanalyzedAt={reanalyzedAt} />)

      // The parent span has tabIndex, not the nested text span
      const textSpan = screen.getByText('Re-analyzed')
      const container = textSpan.parentElement
      expect(container).toHaveAttribute('tabindex', '0')
    })
  })

  describe('Tooltip Content', () => {
    it('shows timestamp on hover (via tooltip trigger)', () => {
      const reanalyzedAt = new Date().toISOString()

      render(<ReanalyzedIndicator reanalyzedAt={reanalyzedAt} />)

      // The parent container span should be present and hoverable
      const textSpan = screen.getByText('Re-analyzed')
      const container = textSpan.parentElement
      expect(container).toHaveClass('cursor-help')
    })
  })
})
