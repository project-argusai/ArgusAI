/**
 * AnalysisModeBadge Component Tests
 *
 * Story P3-3.4: Tests for the analysis mode badge component
 *
 * Demonstrates:
 * - Testing components with props
 * - Testing conditional rendering
 * - Testing with Radix UI components (Tooltip)
 * - Accessibility testing
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TooltipProvider } from '@/components/ui/tooltip'
import { AnalysisModeBadge } from '@/components/events/AnalysisModeBadge'

// Wrapper to provide TooltipProvider context
const renderWithTooltip = (ui: React.ReactElement) => {
  return render(<TooltipProvider>{ui}</TooltipProvider>)
}

describe('AnalysisModeBadge', () => {
  describe('rendering', () => {
    it('returns null when analysisMode is undefined', () => {
      const { container } = renderWithTooltip(
        <AnalysisModeBadge analysisMode={undefined} />
      )

      expect(container).toBeEmptyDOMElement()
    })

    it('returns null when analysisMode is null', () => {
      const { container } = renderWithTooltip(
        <AnalysisModeBadge analysisMode={null} />
      )

      expect(container).toBeEmptyDOMElement()
    })

    it('renders single_frame badge with correct abbreviation', () => {
      renderWithTooltip(<AnalysisModeBadge analysisMode="single_frame" />)

      expect(screen.getByText('SF')).toBeInTheDocument()
    })

    it('renders multi_frame badge with correct abbreviation', () => {
      renderWithTooltip(<AnalysisModeBadge analysisMode="multi_frame" />)

      expect(screen.getByText('MF')).toBeInTheDocument()
    })

    it('renders video_native badge with correct abbreviation', () => {
      renderWithTooltip(<AnalysisModeBadge analysisMode="video_native" />)

      expect(screen.getByText('VN')).toBeInTheDocument()
    })
  })

  describe('styling', () => {
    it('applies gray styling for single_frame', () => {
      renderWithTooltip(<AnalysisModeBadge analysisMode="single_frame" />)

      const badge = screen.getByText('SF').parentElement
      expect(badge).toHaveClass('bg-gray-100')
    })

    it('applies blue styling for multi_frame', () => {
      renderWithTooltip(<AnalysisModeBadge analysisMode="multi_frame" />)

      const badge = screen.getByText('MF').parentElement
      expect(badge).toHaveClass('bg-blue-100')
    })

    it('applies purple styling for video_native', () => {
      renderWithTooltip(<AnalysisModeBadge analysisMode="video_native" />)

      const badge = screen.getByText('VN').parentElement
      expect(badge).toHaveClass('bg-purple-100')
    })
  })

  describe('frame count display', () => {
    it('does not show frame count for single_frame mode', () => {
      renderWithTooltip(
        <AnalysisModeBadge analysisMode="single_frame" frameCountUsed={1} />
      )

      expect(screen.queryByText(/frames analyzed/i)).not.toBeInTheDocument()
    })

    it('shows frame count in tooltip for multi_frame mode', async () => {
      const user = userEvent.setup()

      renderWithTooltip(
        <AnalysisModeBadge analysisMode="multi_frame" frameCountUsed={5} />
      )

      // Hover to show tooltip
      const badge = screen.getByText('MF').parentElement!
      await user.hover(badge)

      // Wait for tooltip to appear - Radix duplicates content for a11y, so use getAllByText
      const frameCountElements = await screen.findAllByText(/frames analyzed: 5/i)
      expect(frameCountElements.length).toBeGreaterThan(0)
    })
  })

  describe('fallback indicator', () => {
    it('does not show fallback indicator when fallbackReason is not provided', () => {
      renderWithTooltip(
        <AnalysisModeBadge analysisMode="single_frame" fallbackReason={null} />
      )

      // The badge should not have the AlertTriangle icon (fallback indicator)
      const badge = screen.getByText('SF').parentElement!
      // Count of icons - should only have 1 (the mode icon)
      const icons = badge.querySelectorAll('svg')
      expect(icons).toHaveLength(1)
    })

    it('shows fallback indicator when fallbackReason is provided', () => {
      renderWithTooltip(
        <AnalysisModeBadge
          analysisMode="single_frame"
          fallbackReason="clip_download_failed"
        />
      )

      const badge = screen.getByText('SF').parentElement!
      // Should have 2 icons - mode icon + fallback warning
      const icons = badge.querySelectorAll('svg')
      expect(icons).toHaveLength(2)
    })

    it('shows fallback reason in tooltip', async () => {
      const user = userEvent.setup()

      renderWithTooltip(
        <AnalysisModeBadge
          analysisMode="single_frame"
          fallbackReason="video_native:provider_unsupported"
        />
      )

      const badge = screen.getByText('SF').parentElement!
      await user.hover(badge)

      // Radix duplicates content for a11y, so use getAllByText
      const fallbackElements = await screen.findAllByText(/video_native:provider_unsupported/i)
      expect(fallbackElements.length).toBeGreaterThan(0)
    })
  })

  describe('accessibility', () => {
    it('includes screen reader text for the mode', () => {
      renderWithTooltip(<AnalysisModeBadge analysisMode="single_frame" />)

      expect(
        screen.getByText(/analysis mode: single frame/i)
      ).toBeInTheDocument()
    })

    it('includes fallback reason in screen reader text when present', () => {
      renderWithTooltip(
        <AnalysisModeBadge
          analysisMode="single_frame"
          fallbackReason="clip_failed"
        />
      )

      expect(
        screen.getByText(/fell back due to: clip_failed/i)
      ).toBeInTheDocument()
    })

    it('has cursor-help class for tooltip interaction hint', () => {
      renderWithTooltip(<AnalysisModeBadge analysisMode="multi_frame" />)

      const badge = screen.getByText('MF').parentElement
      expect(badge).toHaveClass('cursor-help')
    })
  })

  describe('tooltip content', () => {
    it('shows full mode name in tooltip', async () => {
      const user = userEvent.setup()

      renderWithTooltip(<AnalysisModeBadge analysisMode="multi_frame" />)

      const badge = screen.getByText('MF').parentElement!
      await user.hover(badge)

      // Radix duplicates content for a11y, so use getAllByText
      const modeNameElements = await screen.findAllByText('Multi-Frame')
      expect(modeNameElements.length).toBeGreaterThan(0)
    })

    it('shows mode description in tooltip', async () => {
      const user = userEvent.setup()

      renderWithTooltip(<AnalysisModeBadge analysisMode="single_frame" />)

      const badge = screen.getByText('SF').parentElement!
      await user.hover(badge)

      // Radix duplicates content for a11y, so use getAllByText
      const descElements = await screen.findAllByText(/uses event thumbnail only/i)
      expect(descElements.length).toBeGreaterThan(0)
    })
  })
})
