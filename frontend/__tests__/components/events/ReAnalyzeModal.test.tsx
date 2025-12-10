/**
 * Tests for ReAnalyzeModal component
 *
 * Story P3-6.4: Modal for selecting re-analysis mode
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '../../test-utils'
import { ReAnalyzeModal } from '@/components/events/ReAnalyzeModal'
import { mockEvent } from '../../test-utils'
import { apiClient } from '@/lib/api-client'
import { toast } from 'sonner'

// Mock API client
vi.mock('@/lib/api-client', () => ({
  apiClient: {
    events: {
      reanalyze: vi.fn(),
    },
  },
}))

// Mock toast
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

describe('ReAnalyzeModal', () => {
  const mockOnClose = vi.fn()
  const mockOnSuccess = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  // AC2: Test mode options display
  describe('AC2: Show Re-Analysis Options Modal', () => {
    it('displays all three analysis modes', () => {
      const event = mockEvent({ source_type: 'protect' })

      render(
        <ReAnalyzeModal
          event={event}
          isOpen={true}
          onClose={mockOnClose}
          onSuccess={mockOnSuccess}
        />
      )

      // There are 3 radio buttons, one for each mode
      expect(screen.getAllByRole('radio')).toHaveLength(3)
      // Check labels exist (they may appear multiple times due to current mode display)
      expect(screen.getAllByText('Single Frame').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('Multi-Frame').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('Video Native').length).toBeGreaterThanOrEqual(1)
    })

    it('shows cost indicators for each mode', () => {
      const event = mockEvent({ source_type: 'protect' })

      render(
        <ReAnalyzeModal
          event={event}
          isOpen={true}
          onClose={mockOnClose}
          onSuccess={mockOnSuccess}
        />
      )

      // Cost indicators: $, $$, $$$
      expect(screen.getByText('$')).toBeInTheDocument()
      expect(screen.getByText('$$')).toBeInTheDocument()
      expect(screen.getByText('$$$')).toBeInTheDocument()
    })

    it('shows current analysis mode', () => {
      const event = mockEvent({ source_type: 'protect', analysis_mode: 'single_frame' })

      render(
        <ReAnalyzeModal
          event={event}
          isOpen={true}
          onClose={mockOnClose}
          onSuccess={mockOnSuccess}
        />
      )

      expect(screen.getByText(/current mode:/i)).toBeInTheDocument()
      // Single Frame appears multiple times (in current mode display and radio option)
      expect(screen.getAllByText('Single Frame').length).toBeGreaterThanOrEqual(1)
    })

    it('disables multi_frame for RTSP cameras', () => {
      const event = mockEvent({ source_type: 'rtsp' })

      render(
        <ReAnalyzeModal
          event={event}
          isOpen={true}
          onClose={mockOnClose}
          onSuccess={mockOnSuccess}
        />
      )

      // Multi-frame radio should be disabled
      const multiFrameRadio = screen.getByRole('radio', { name: /multi-frame/i })
      expect(multiFrameRadio).toBeDisabled()
    })

    it('disables video_native for USB cameras', () => {
      const event = mockEvent({ source_type: 'usb' })

      render(
        <ReAnalyzeModal
          event={event}
          isOpen={true}
          onClose={mockOnClose}
          onSuccess={mockOnSuccess}
        />
      )

      // Video native radio should be disabled
      const videoNativeRadio = screen.getByRole('radio', { name: /video native/i })
      expect(videoNativeRadio).toBeDisabled()
    })

    it('shows explanation why mode is disabled', () => {
      const event = mockEvent({ source_type: 'rtsp' })

      render(
        <ReAnalyzeModal
          event={event}
          isOpen={true}
          onClose={mockOnClose}
          onSuccess={mockOnSuccess}
        />
      )

      // Two modes are disabled for RTSP (multi_frame and video_native), so there are 2 explanations
      const explanations = screen.getAllByText(/requires a UniFi Protect camera/i)
      expect(explanations.length).toBeGreaterThanOrEqual(1)
    })

    it('enables all modes for Protect cameras', () => {
      const event = mockEvent({ source_type: 'protect' })

      render(
        <ReAnalyzeModal
          event={event}
          isOpen={true}
          onClose={mockOnClose}
          onSuccess={mockOnSuccess}
        />
      )

      const radios = screen.getAllByRole('radio')
      radios.forEach((radio) => {
        expect(radio).not.toBeDisabled()
      })
    })
  })

  // AC3: Test API call trigger
  describe('AC3: Trigger Re-Analysis via API', () => {
    it('calls API with selected mode when confirm is clicked', async () => {
      const event = mockEvent({ source_type: 'protect' })
      const updatedEvent = mockEvent({ ...event, ai_confidence: 90 })
      vi.mocked(apiClient.events.reanalyze).mockResolvedValue(updatedEvent)

      const { user } = render(
        <ReAnalyzeModal
          event={event}
          isOpen={true}
          onClose={mockOnClose}
          onSuccess={mockOnSuccess}
        />
      )

      // Click confirm
      await user.click(screen.getByRole('button', { name: /confirm/i }))

      await waitFor(() => {
        expect(apiClient.events.reanalyze).toHaveBeenCalledWith(
          event.id,
          'single_frame' // Default selected mode
        )
      })
    })

    it('shows loading state during API call', async () => {
      const event = mockEvent({ source_type: 'protect' })
      // Create a promise that we can control
      let resolvePromise: (value: unknown) => void
      const pendingPromise = new Promise((resolve) => {
        resolvePromise = resolve
      })
      vi.mocked(apiClient.events.reanalyze).mockReturnValue(pendingPromise as Promise<ReturnType<typeof mockEvent>>)

      const { user } = render(
        <ReAnalyzeModal
          event={event}
          isOpen={true}
          onClose={mockOnClose}
          onSuccess={mockOnSuccess}
        />
      )

      await user.click(screen.getByRole('button', { name: /confirm/i }))

      // Should show loading state
      expect(screen.getByText(/re-analyzing/i)).toBeInTheDocument()

      // Clean up
      resolvePromise!(mockEvent())
    })
  })

  // AC4: Test success handling
  describe('AC4: Update Event with New Description', () => {
    it('shows success toast on successful re-analysis', async () => {
      const event = mockEvent({ source_type: 'protect' })
      const updatedEvent = mockEvent({ ...event, ai_confidence: 90 })
      vi.mocked(apiClient.events.reanalyze).mockResolvedValue(updatedEvent)

      const { user } = render(
        <ReAnalyzeModal
          event={event}
          isOpen={true}
          onClose={mockOnClose}
          onSuccess={mockOnSuccess}
        />
      )

      await user.click(screen.getByRole('button', { name: /confirm/i }))

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith(
          'Event re-analyzed successfully',
          expect.any(Object)
        )
      })
    })

    it('calls onSuccess callback with updated event', async () => {
      const event = mockEvent({ source_type: 'protect' })
      const updatedEvent = mockEvent({ ...event, ai_confidence: 90 })
      vi.mocked(apiClient.events.reanalyze).mockResolvedValue(updatedEvent)

      const { user } = render(
        <ReAnalyzeModal
          event={event}
          isOpen={true}
          onClose={mockOnClose}
          onSuccess={mockOnSuccess}
        />
      )

      await user.click(screen.getByRole('button', { name: /confirm/i }))

      await waitFor(() => {
        expect(mockOnSuccess).toHaveBeenCalledWith(updatedEvent)
      })
    })
  })

  // AC5: Test error handling
  describe('AC5: Handle Re-Analysis Failure', () => {
    it('shows error toast on API failure', async () => {
      const event = mockEvent({ source_type: 'protect' })
      vi.mocked(apiClient.events.reanalyze).mockRejectedValue(new Error('API error'))

      const { user } = render(
        <ReAnalyzeModal
          event={event}
          isOpen={true}
          onClose={mockOnClose}
          onSuccess={mockOnSuccess}
        />
      )

      await user.click(screen.getByRole('button', { name: /confirm/i }))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(
          'Re-analysis failed',
          expect.any(Object)
        )
      })
    })

    it('shows rate limit error message for 429 response', async () => {
      const event = mockEvent({ source_type: 'protect' })
      vi.mocked(apiClient.events.reanalyze).mockRejectedValue(new Error('429 Too Many Requests'))

      const { user } = render(
        <ReAnalyzeModal
          event={event}
          isOpen={true}
          onClose={mockOnClose}
          onSuccess={mockOnSuccess}
        />
      )

      await user.click(screen.getByRole('button', { name: /confirm/i }))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(
          'Re-analysis failed',
          expect.objectContaining({
            description: expect.stringContaining('Rate limit exceeded'),
          })
        )
      })
    })
  })

  describe('Modal Controls', () => {
    it('closes when cancel is clicked', async () => {
      const event = mockEvent({ source_type: 'protect' })

      const { user } = render(
        <ReAnalyzeModal
          event={event}
          isOpen={true}
          onClose={mockOnClose}
          onSuccess={mockOnSuccess}
        />
      )

      await user.click(screen.getByRole('button', { name: /cancel/i }))

      expect(mockOnClose).toHaveBeenCalled()
    })

    it('shows re-analysis count if event has been re-analyzed before', () => {
      const event = mockEvent({ source_type: 'protect', reanalysis_count: 2 })

      render(
        <ReAnalyzeModal
          event={event}
          isOpen={true}
          onClose={mockOnClose}
          onSuccess={mockOnSuccess}
        />
      )

      expect(screen.getByText(/re-analyzed 2 times/i)).toBeInTheDocument()
    })
  })
})
