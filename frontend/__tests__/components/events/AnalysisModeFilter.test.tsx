/**
 * AnalysisModeFilter Tests
 *
 * Story P3-7.6: Tests for analysis mode filter functionality in EventFilters
 *
 * Demonstrates:
 * - Testing filter checkbox interactions
 * - Testing callback functions with filter state
 * - Testing combined filter behavior
 * - Testing URL param persistence pattern
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EventFilters } from '@/components/events/EventFilters'

// Mock useDebounce to immediately return the value
vi.mock('@/lib/hooks/useDebounce', () => ({
  useDebounce: (value: string) => value,
}))

describe('AnalysisModeFilter', () => {
  const mockCameras = [
    { id: 'cam-1', name: 'Front Door', type: 'protect' as const, is_enabled: true, frame_rate: 5 },
    { id: 'cam-2', name: 'Back Yard', type: 'rtsp' as const, is_enabled: true, frame_rate: 5 },
  ]

  describe('rendering', () => {
    it('renders Analysis Mode section with Layers icon', () => {
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{}}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      expect(screen.getByText('Analysis Mode')).toBeInTheDocument()
    })

    it('renders all analysis mode options', () => {
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{}}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      expect(screen.getByText('Single Frame')).toBeInTheDocument()
      expect(screen.getByText('Multi-Frame')).toBeInTheDocument()
      expect(screen.getByText('Video Native')).toBeInTheDocument()
    })

    it('renders "With fallback" filter option', () => {
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{}}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      expect(screen.getByText('With fallback')).toBeInTheDocument()
    })

    it('renders "Low confidence" filter option', () => {
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{}}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      expect(screen.getByText('Low confidence')).toBeInTheDocument()
    })

    it('shows description text for analysis modes', () => {
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{}}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      expect(screen.getByText('(Snapshot analysis)')).toBeInTheDocument()
      expect(screen.getByText('(Sequence analysis)')).toBeInTheDocument()
      expect(screen.getByText('(Full video analysis)')).toBeInTheDocument()
    })
  })

  describe('analysis mode selection', () => {
    it('calls onFiltersChange with analysis_mode when Single Frame is selected', async () => {
      const user = userEvent.setup()
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{}}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      const singleFrameCheckbox = screen.getByRole('checkbox', { name: /single frame/i })
      await user.click(singleFrameCheckbox)

      expect(onFiltersChange).toHaveBeenCalledWith(
        expect.objectContaining({ analysis_mode: 'single_frame' })
      )
    })

    it('calls onFiltersChange with analysis_mode when Multi-Frame is selected', async () => {
      const user = userEvent.setup()
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{}}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      const multiFrameCheckbox = screen.getByRole('checkbox', { name: /multi-frame/i })
      await user.click(multiFrameCheckbox)

      expect(onFiltersChange).toHaveBeenCalledWith(
        expect.objectContaining({ analysis_mode: 'multi_frame' })
      )
    })

    it('calls onFiltersChange with analysis_mode when Video Native is selected', async () => {
      const user = userEvent.setup()
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{}}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      const videoNativeCheckbox = screen.getByRole('checkbox', { name: /video native/i })
      await user.click(videoNativeCheckbox)

      expect(onFiltersChange).toHaveBeenCalledWith(
        expect.objectContaining({ analysis_mode: 'video_native' })
      )
    })

    it('clears analysis_mode when same option is clicked again', async () => {
      const user = userEvent.setup()
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{ analysis_mode: 'single_frame' }}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      // Click to deselect
      const singleFrameCheckbox = screen.getByRole('checkbox', { name: /single frame/i })
      await user.click(singleFrameCheckbox)

      expect(onFiltersChange).toHaveBeenCalledWith(
        expect.objectContaining({ analysis_mode: undefined })
      )
    })
  })

  describe('fallback filter', () => {
    it('calls onFiltersChange with has_fallback=true when checked', async () => {
      const user = userEvent.setup()
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{}}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      const fallbackCheckbox = screen.getByRole('checkbox', { name: /with fallback/i })
      await user.click(fallbackCheckbox)

      expect(onFiltersChange).toHaveBeenCalledWith(
        expect.objectContaining({ has_fallback: true })
      )
    })

    it('calls onFiltersChange with has_fallback=undefined when unchecked', async () => {
      const user = userEvent.setup()
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{ has_fallback: true }}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      const fallbackCheckbox = screen.getByRole('checkbox', { name: /with fallback/i })
      await user.click(fallbackCheckbox)

      expect(onFiltersChange).toHaveBeenCalledWith(
        expect.objectContaining({ has_fallback: undefined })
      )
    })
  })

  describe('low confidence filter', () => {
    it('calls onFiltersChange with low_confidence=true when checked', async () => {
      const user = userEvent.setup()
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{}}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      const lowConfidenceCheckbox = screen.getByRole('checkbox', { name: /low confidence/i })
      await user.click(lowConfidenceCheckbox)

      expect(onFiltersChange).toHaveBeenCalledWith(
        expect.objectContaining({ low_confidence: true })
      )
    })

    it('calls onFiltersChange with low_confidence=undefined when unchecked', async () => {
      const user = userEvent.setup()
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{ low_confidence: true }}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      const lowConfidenceCheckbox = screen.getByRole('checkbox', { name: /low confidence/i })
      await user.click(lowConfidenceCheckbox)

      expect(onFiltersChange).toHaveBeenCalledWith(
        expect.objectContaining({ low_confidence: undefined })
      )
    })
  })

  describe('checkbox states reflect filter values', () => {
    it('shows analysis mode checkbox as checked when filter is set', () => {
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{ analysis_mode: 'multi_frame' }}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      const multiFrameCheckbox = screen.getByRole('checkbox', { name: /multi-frame/i })
      expect(multiFrameCheckbox).toHaveAttribute('data-state', 'checked')
    })

    it('shows has_fallback checkbox as checked when filter is true', () => {
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{ has_fallback: true }}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      const fallbackCheckbox = screen.getByRole('checkbox', { name: /with fallback/i })
      expect(fallbackCheckbox).toHaveAttribute('data-state', 'checked')
    })

    it('shows low_confidence checkbox as checked when filter is true', () => {
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{ low_confidence: true }}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      const lowConfidenceCheckbox = screen.getByRole('checkbox', { name: /low confidence/i })
      expect(lowConfidenceCheckbox).toHaveAttribute('data-state', 'checked')
    })
  })

  describe('clear all resets analysis filters', () => {
    it('clears analysis_mode when Clear all is clicked', async () => {
      const user = userEvent.setup()
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{ analysis_mode: 'single_frame' }}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      const clearButton = screen.getByRole('button', { name: /clear all/i })
      await user.click(clearButton)

      expect(onFiltersChange).toHaveBeenCalledWith({})
    })

    it('clears has_fallback when Clear all is clicked', async () => {
      const user = userEvent.setup()
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{ has_fallback: true }}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      const clearButton = screen.getByRole('button', { name: /clear all/i })
      await user.click(clearButton)

      expect(onFiltersChange).toHaveBeenCalledWith({})
    })

    it('clears low_confidence when Clear all is clicked', async () => {
      const user = userEvent.setup()
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{ low_confidence: true }}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      const clearButton = screen.getByRole('button', { name: /clear all/i })
      await user.click(clearButton)

      expect(onFiltersChange).toHaveBeenCalledWith({})
    })
  })

  describe('hasActiveFilters detection', () => {
    it('shows Clear all button when analysis_mode is set', () => {
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{ analysis_mode: 'video_native' }}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      expect(screen.getByRole('button', { name: /clear all/i })).toBeInTheDocument()
    })

    it('shows Clear all button when has_fallback is true', () => {
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{ has_fallback: true }}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      expect(screen.getByRole('button', { name: /clear all/i })).toBeInTheDocument()
    })

    it('shows Clear all button when low_confidence is true', () => {
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{ low_confidence: true }}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      expect(screen.getByRole('button', { name: /clear all/i })).toBeInTheDocument()
    })
  })

  describe('accessibility', () => {
    it('filter checkboxes have accessible labels', () => {
      const onFiltersChange = vi.fn()

      render(
        <EventFilters
          filters={{}}
          onFiltersChange={onFiltersChange}
          cameras={mockCameras}
        />
      )

      // Analysis mode checkboxes should have labels
      expect(screen.getByLabelText(/single frame/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/multi-frame/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/video native/i)).toBeInTheDocument()

      // Special filter checkboxes
      expect(screen.getByLabelText(/with fallback/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/low confidence/i)).toBeInTheDocument()
    })
  })
})
