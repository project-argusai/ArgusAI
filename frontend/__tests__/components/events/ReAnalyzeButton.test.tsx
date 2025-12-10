/**
 * Tests for ReAnalyzeButton component
 *
 * Story P3-6.4: Re-analyze button for low-confidence events
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '../../test-utils'
import { ReAnalyzeButton } from '@/components/events/ReAnalyzeButton'
import { mockEvent } from '../../test-utils'

// Mock the ReAnalyzeModal component to simplify testing
vi.mock('@/components/events/ReAnalyzeModal', () => ({
  ReAnalyzeModal: vi.fn(({ isOpen }) =>
    isOpen ? <div data-testid="reanalyze-modal">Modal</div> : null
  ),
}))

describe('ReAnalyzeButton', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // AC1: Test button only shows for low confidence events
  describe('AC1: Display Re-Analyze Button on Low Confidence Events', () => {
    it('renders button when event.low_confidence is true', () => {
      const event = mockEvent({ low_confidence: true })

      render(<ReAnalyzeButton event={event} />)

      expect(screen.getByRole('button', { name: /re-analyze/i })).toBeInTheDocument()
    })

    it('does not render button when event.low_confidence is false', () => {
      const event = mockEvent({ low_confidence: false })

      render(<ReAnalyzeButton event={event} />)

      expect(screen.queryByRole('button')).not.toBeInTheDocument()
    })

    it('does not render button when event.low_confidence is undefined', () => {
      const event = mockEvent({ low_confidence: undefined })

      render(<ReAnalyzeButton event={event} />)

      expect(screen.queryByRole('button')).not.toBeInTheDocument()
    })
  })

  describe('Button Styling and Icon', () => {
    it('uses RefreshCw icon', () => {
      const event = mockEvent({ low_confidence: true })

      render(<ReAnalyzeButton event={event} />)

      // The button should contain an SVG (the icon)
      const button = screen.getByRole('button', { name: /re-analyze/i })
      expect(button.querySelector('svg')).toBeInTheDocument()
    })

    it('has screen reader text', () => {
      const event = mockEvent({ low_confidence: true })

      render(<ReAnalyzeButton event={event} />)

      expect(screen.getByText('Re-analyze')).toHaveClass('sr-only')
    })
  })

  describe('Loading State', () => {
    it('shows loading animation when isLoading is true', () => {
      const event = mockEvent({ low_confidence: true })

      render(<ReAnalyzeButton event={event} isLoading={true} />)

      const button = screen.getByRole('button')
      expect(button).toBeDisabled()
      // Check for animate-spin class on the icon
      const svg = button.querySelector('svg')
      expect(svg).toHaveClass('animate-spin')
    })

    it('button is enabled when isLoading is false', () => {
      const event = mockEvent({ low_confidence: true })

      render(<ReAnalyzeButton event={event} isLoading={false} />)

      expect(screen.getByRole('button')).not.toBeDisabled()
    })
  })

  describe('Modal Integration', () => {
    it('opens modal when button is clicked', async () => {
      const event = mockEvent({ low_confidence: true })

      const { user } = render(<ReAnalyzeButton event={event} />)

      // Initially no modal
      expect(screen.queryByTestId('reanalyze-modal')).not.toBeInTheDocument()

      // Click button
      await user.click(screen.getByRole('button'))

      // Modal should now be visible
      expect(screen.getByTestId('reanalyze-modal')).toBeInTheDocument()
    })
  })
})
