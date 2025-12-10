/**
 * ConfidenceIndicator Component Tests
 *
 * Story P3-6.3: Tests for the AI confidence indicator component
 *
 * Tests cover:
 * - AC1: Display confidence score with visual treatment (high/medium/low)
 * - AC2: Display low confidence warning
 * - AC3: Show confidence tooltip with explanation
 * - AC4: Handle missing confidence gracefully
 * - AC5: Show vague reason in tooltip
 * - AC6: Accessibility support
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TooltipProvider } from '@/components/ui/tooltip'
import { ConfidenceIndicator } from '@/components/events/ConfidenceIndicator'

// Wrapper to provide TooltipProvider context
const renderWithTooltip = (ui: React.ReactElement) => {
  return render(<TooltipProvider>{ui}</TooltipProvider>)
}

describe('ConfidenceIndicator', () => {
  describe('AC4: Handle Missing Confidence', () => {
    it('returns null when aiConfidence is undefined', () => {
      const { container } = renderWithTooltip(
        <ConfidenceIndicator aiConfidence={undefined} />
      )

      expect(container).toBeEmptyDOMElement()
    })

    it('returns null when aiConfidence is null', () => {
      const { container } = renderWithTooltip(
        <ConfidenceIndicator aiConfidence={null} />
      )

      expect(container).toBeEmptyDOMElement()
    })
  })

  describe('AC1: Display Confidence Score Indicator', () => {
    it('renders high confidence (85) with green styling', () => {
      renderWithTooltip(<ConfidenceIndicator aiConfidence={85} />)

      expect(screen.getByText('85%')).toBeInTheDocument()
      const badge = screen.getByText('85%').parentElement
      expect(badge).toHaveClass('bg-green-100')
      expect(badge).toHaveClass('text-green-700')
    })

    it('renders high confidence (80) at threshold with green styling', () => {
      renderWithTooltip(<ConfidenceIndicator aiConfidence={80} />)

      expect(screen.getByText('80%')).toBeInTheDocument()
      const badge = screen.getByText('80%').parentElement
      expect(badge).toHaveClass('bg-green-100')
    })

    it('renders high confidence (100) with green styling', () => {
      renderWithTooltip(<ConfidenceIndicator aiConfidence={100} />)

      expect(screen.getByText('100%')).toBeInTheDocument()
      const badge = screen.getByText('100%').parentElement
      expect(badge).toHaveClass('bg-green-100')
    })

    it('renders medium confidence (65) with amber styling', () => {
      renderWithTooltip(<ConfidenceIndicator aiConfidence={65} />)

      expect(screen.getByText('65%')).toBeInTheDocument()
      const badge = screen.getByText('65%').parentElement
      expect(badge).toHaveClass('bg-amber-100')
      expect(badge).toHaveClass('text-amber-700')
    })

    it('renders medium confidence (50) at threshold with amber styling', () => {
      renderWithTooltip(<ConfidenceIndicator aiConfidence={50} />)

      expect(screen.getByText('50%')).toBeInTheDocument()
      const badge = screen.getByText('50%').parentElement
      expect(badge).toHaveClass('bg-amber-100')
    })

    it('renders medium confidence (79) at upper bound with amber styling', () => {
      renderWithTooltip(<ConfidenceIndicator aiConfidence={79} />)

      expect(screen.getByText('79%')).toBeInTheDocument()
      const badge = screen.getByText('79%').parentElement
      expect(badge).toHaveClass('bg-amber-100')
    })

    it('renders low confidence (35) with red styling', () => {
      renderWithTooltip(<ConfidenceIndicator aiConfidence={35} />)

      expect(screen.getByText('35%')).toBeInTheDocument()
      const badge = screen.getByText('35%').parentElement
      expect(badge).toHaveClass('bg-red-100')
      expect(badge).toHaveClass('text-red-700')
    })

    it('renders low confidence (0) with red styling', () => {
      renderWithTooltip(<ConfidenceIndicator aiConfidence={0} />)

      expect(screen.getByText('0%')).toBeInTheDocument()
      const badge = screen.getByText('0%').parentElement
      expect(badge).toHaveClass('bg-red-100')
    })

    it('renders low confidence (49) at upper bound with red styling', () => {
      renderWithTooltip(<ConfidenceIndicator aiConfidence={49} />)

      expect(screen.getByText('49%')).toBeInTheDocument()
      const badge = screen.getByText('49%').parentElement
      expect(badge).toHaveClass('bg-red-100')
    })

    it('renders with appropriate icon for each level', () => {
      // High confidence should have CheckCircle2 icon
      const { unmount: unmount1 } = renderWithTooltip(
        <ConfidenceIndicator aiConfidence={85} />
      )
      let badge = screen.getByText('85%').parentElement!
      expect(badge.querySelectorAll('svg')).toHaveLength(1)
      unmount1()

      // Medium confidence should have Circle icon
      const { unmount: unmount2 } = renderWithTooltip(
        <ConfidenceIndicator aiConfidence={65} />
      )
      badge = screen.getByText('65%').parentElement!
      expect(badge.querySelectorAll('svg')).toHaveLength(1)
      unmount2()

      // Low confidence should have AlertTriangle icon
      renderWithTooltip(<ConfidenceIndicator aiConfidence={35} />)
      badge = screen.getByText('35%').parentElement!
      expect(badge.querySelectorAll('svg')).toHaveLength(1)
    })
  })

  describe('AC2: Display Low Confidence Warning', () => {
    it('shows warning icon when lowConfidence is true and level is high', () => {
      renderWithTooltip(
        <ConfidenceIndicator aiConfidence={85} lowConfidence={true} />
      )

      const badge = screen.getByText('85%').parentElement!
      // Should have 2 icons - main icon + warning triangle
      expect(badge.querySelectorAll('svg')).toHaveLength(2)
    })

    it('shows warning icon when lowConfidence is true and level is medium', () => {
      renderWithTooltip(
        <ConfidenceIndicator aiConfidence={65} lowConfidence={true} />
      )

      const badge = screen.getByText('65%').parentElement!
      // Should have 2 icons - main icon + warning triangle
      expect(badge.querySelectorAll('svg')).toHaveLength(2)
    })

    it('does not show extra warning icon for low confidence level (already has triangle)', () => {
      renderWithTooltip(
        <ConfidenceIndicator aiConfidence={35} lowConfidence={true} />
      )

      const badge = screen.getByText('35%').parentElement!
      // Should only have 1 icon - the AlertTriangle is already the main icon
      expect(badge.querySelectorAll('svg')).toHaveLength(1)
    })

    it('does not show warning icon when lowConfidence is false', () => {
      renderWithTooltip(
        <ConfidenceIndicator aiConfidence={85} lowConfidence={false} />
      )

      const badge = screen.getByText('85%').parentElement!
      // Should only have 1 icon
      expect(badge.querySelectorAll('svg')).toHaveLength(1)
    })

    it('does not show warning icon when lowConfidence is undefined', () => {
      renderWithTooltip(
        <ConfidenceIndicator aiConfidence={85} />
      )

      const badge = screen.getByText('85%').parentElement!
      expect(badge.querySelectorAll('svg')).toHaveLength(1)
    })
  })

  describe('AC3: Show Confidence Tooltip', () => {
    it('shows tooltip with confidence percentage on hover', async () => {
      const user = userEvent.setup()

      renderWithTooltip(<ConfidenceIndicator aiConfidence={85} />)

      const badge = screen.getByText('85%').parentElement!
      await user.hover(badge)

      // Radix duplicates content for a11y, so use getAllByText
      const confidenceElements = await screen.findAllByText(/Confidence: 85%/i)
      expect(confidenceElements.length).toBeGreaterThan(0)
    })

    it('shows high confidence explanation in tooltip', async () => {
      const user = userEvent.setup()

      renderWithTooltip(<ConfidenceIndicator aiConfidence={85} />)

      const badge = screen.getByText('85%').parentElement!
      await user.hover(badge)

      const descElements = await screen.findAllByText(/AI is certain about this description/i)
      expect(descElements.length).toBeGreaterThan(0)
    })

    it('shows medium confidence explanation in tooltip', async () => {
      const user = userEvent.setup()

      renderWithTooltip(<ConfidenceIndicator aiConfidence={65} />)

      const badge = screen.getByText('65%').parentElement!
      await user.hover(badge)

      const descElements = await screen.findAllByText(/Description may need verification/i)
      expect(descElements.length).toBeGreaterThan(0)
    })

    it('shows low confidence explanation in tooltip', async () => {
      const user = userEvent.setup()

      renderWithTooltip(<ConfidenceIndicator aiConfidence={35} />)

      const badge = screen.getByText('35%').parentElement!
      await user.hover(badge)

      const descElements = await screen.findAllByText(/Consider re-analyzing this event/i)
      expect(descElements.length).toBeGreaterThan(0)
    })

    it('shows low confidence warning in tooltip when flagged', async () => {
      const user = userEvent.setup()

      renderWithTooltip(
        <ConfidenceIndicator aiConfidence={85} lowConfidence={true} />
      )

      const badge = screen.getByText('85%').parentElement!
      await user.hover(badge)

      const warningElements = await screen.findAllByText(/AI was uncertain about this description/i)
      expect(warningElements.length).toBeGreaterThan(0)
    })
  })

  describe('AC5: Show Vague Reason in Tooltip', () => {
    it('shows vague reason in tooltip when present', async () => {
      const user = userEvent.setup()

      renderWithTooltip(
        <ConfidenceIndicator
          aiConfidence={35}
          lowConfidence={true}
          vagueReason="Contains vague phrase: 'appears to be'"
        />
      )

      const badge = screen.getByText('35%').parentElement!
      await user.hover(badge)

      const reasonElements = await screen.findAllByText(/Reason: Contains vague phrase/i)
      expect(reasonElements.length).toBeGreaterThan(0)
    })

    it('does not show vague reason when null', async () => {
      const user = userEvent.setup()

      renderWithTooltip(
        <ConfidenceIndicator
          aiConfidence={35}
          lowConfidence={true}
          vagueReason={null}
        />
      )

      const badge = screen.getByText('35%').parentElement!
      await user.hover(badge)

      // Wait for tooltip to appear
      await screen.findAllByText(/Confidence: 35%/i)

      // Should not have "Reason:" text
      expect(screen.queryByText(/Reason:/i)).not.toBeInTheDocument()
    })

    it('does not show vague reason when undefined', async () => {
      const user = userEvent.setup()

      renderWithTooltip(
        <ConfidenceIndicator aiConfidence={35} lowConfidence={true} />
      )

      const badge = screen.getByText('35%').parentElement!
      await user.hover(badge)

      // Wait for tooltip to appear
      await screen.findAllByText(/Confidence: 35%/i)

      // Should not have "Reason:" text
      expect(screen.queryByText(/Reason:/i)).not.toBeInTheDocument()
    })
  })

  describe('AC6: Accessibility Support', () => {
    it('includes screen reader text for high confidence', () => {
      renderWithTooltip(<ConfidenceIndicator aiConfidence={92} />)

      expect(
        screen.getByText(/High confidence: 92%/i)
      ).toBeInTheDocument()
    })

    it('includes screen reader text for medium confidence', () => {
      renderWithTooltip(<ConfidenceIndicator aiConfidence={65} />)

      expect(
        screen.getByText(/Medium confidence: 65%/i)
      ).toBeInTheDocument()
    })

    it('includes screen reader text for low confidence', () => {
      renderWithTooltip(<ConfidenceIndicator aiConfidence={35} />)

      expect(
        screen.getByText(/Low confidence: 35%/i)
      ).toBeInTheDocument()
    })

    it('includes low confidence warning in screen reader text when flagged', () => {
      renderWithTooltip(
        <ConfidenceIndicator aiConfidence={85} lowConfidence={true} />
      )

      expect(
        screen.getByText(/AI was uncertain about this description/i)
      ).toBeInTheDocument()
    })

    it('includes vague reason in screen reader text when present', () => {
      renderWithTooltip(
        <ConfidenceIndicator
          aiConfidence={35}
          lowConfidence={true}
          vagueReason="Too short"
        />
      )

      expect(
        screen.getByText(/Reason: Too short/i)
      ).toBeInTheDocument()
    })

    it('has cursor-help class for tooltip interaction hint', () => {
      renderWithTooltip(<ConfidenceIndicator aiConfidence={85} />)

      const badge = screen.getByText('85%').parentElement
      expect(badge).toHaveClass('cursor-help')
    })

    it('is keyboard focusable via tabIndex', () => {
      renderWithTooltip(<ConfidenceIndicator aiConfidence={85} />)

      const badge = screen.getByText('85%').parentElement
      expect(badge).toHaveAttribute('tabindex', '0')
    })
  })

  describe('styling consistency', () => {
    it('uses consistent badge styling pattern', () => {
      renderWithTooltip(<ConfidenceIndicator aiConfidence={85} />)

      const badge = screen.getByText('85%').parentElement
      expect(badge).toHaveClass('inline-flex')
      expect(badge).toHaveClass('items-center')
      expect(badge).toHaveClass('gap-1')
      expect(badge).toHaveClass('px-1.5')
      expect(badge).toHaveClass('py-0.5')
      expect(badge).toHaveClass('rounded')
      expect(badge).toHaveClass('text-xs')
      expect(badge).toHaveClass('font-medium')
    })
  })
})
