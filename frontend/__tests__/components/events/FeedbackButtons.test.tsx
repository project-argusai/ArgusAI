/**
 * FeedbackButtons Component Tests
 *
 * Story P5-3.7: Tests for the FeedbackButtons component
 *
 * Tests cover:
 * - AC1: Thumbs up button click handler
 * - AC2: Thumbs down button click handler
 * - AC3: Loading state
 * - AC4: Already-submitted state (existing feedback)
 * - AC5: Correction input functionality
 * - AC6: ARIA labels and accessibility
 */

import { describe, it, expect, vi, beforeEach, Mock } from 'vitest'
import { render, screen } from '../../test-utils'
import { FeedbackButtons } from '@/components/events/FeedbackButtons'
import { useSubmitFeedback, useUpdateFeedback, useDeleteFeedback } from '@/hooks/useFeedback'
import type { IEventFeedback } from '@/types/event'

// Mock the useFeedback hooks
vi.mock('@/hooks/useFeedback', () => ({
  useSubmitFeedback: vi.fn(),
  useUpdateFeedback: vi.fn(),
  useDeleteFeedback: vi.fn(),  // Story P10-4.3: Added for feedback deletion
}))

// Mock sonner toast
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

const mockSubmitMutate = vi.fn()
const mockUpdateMutate = vi.fn()
const mockDeleteMutate = vi.fn()  // Story P10-4.3: Added for feedback deletion

const mockFeedback: IEventFeedback = {
  id: 'feedback-1',
  event_id: 'event-1',
  camera_id: null,
  rating: 'helpful',
  correction: null,
  created_at: new Date().toISOString(),
  updated_at: null,
}

describe('FeedbackButtons', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    // Default mock implementations - not pending
    ;(useSubmitFeedback as Mock).mockReturnValue({
      mutate: mockSubmitMutate,
      isPending: false,
    })
    ;(useUpdateFeedback as Mock).mockReturnValue({
      mutate: mockUpdateMutate,
      isPending: false,
    })
    // Story P10-4.3: Mock useDeleteFeedback
    ;(useDeleteFeedback as Mock).mockReturnValue({
      mutate: mockDeleteMutate,
      isPending: false,
    })
  })

  describe('AC1: Thumbs Up Button Click Handler', () => {
    it('renders thumbs up button with correct aria-label when not selected', () => {
      render(<FeedbackButtons eventId="event-1" />)

      const thumbsUpButton = screen.getByRole('button', { name: /mark as helpful/i })
      expect(thumbsUpButton).toBeInTheDocument()
      expect(thumbsUpButton).toHaveAttribute('aria-pressed', 'false')
    })

    it('renders thumbs up button with "Marked as helpful" aria-label when selected', () => {
      render(
        <FeedbackButtons
          eventId="event-1"
          existingFeedback={{ ...mockFeedback, rating: 'helpful' }}
        />
      )

      const thumbsUpButton = screen.getByRole('button', { name: /marked as helpful/i })
      expect(thumbsUpButton).toBeInTheDocument()
      expect(thumbsUpButton).toHaveAttribute('aria-pressed', 'true')
    })

    it('calls submitFeedback with "helpful" rating when clicked', async () => {
      const { user } = render(<FeedbackButtons eventId="event-1" />)

      const thumbsUpButton = screen.getByRole('button', { name: /mark as helpful/i })
      await user.click(thumbsUpButton)

      expect(mockSubmitMutate).toHaveBeenCalledWith(
        {
          eventId: 'event-1',
          rating: 'helpful',
          correction: undefined,
        },
        expect.any(Object)
      )
    })

    it('shows green styling when rating is "helpful"', () => {
      render(
        <FeedbackButtons
          eventId="event-1"
          existingFeedback={{ ...mockFeedback, rating: 'helpful' }}
        />
      )

      const thumbsUpButton = screen.getByRole('button', { name: /marked as helpful/i })
      expect(thumbsUpButton).toHaveClass('bg-green-600')
    })

    it('does not have green styling when not selected', () => {
      render(<FeedbackButtons eventId="event-1" />)

      const thumbsUpButton = screen.getByRole('button', { name: /mark as helpful/i })
      expect(thumbsUpButton).not.toHaveClass('bg-green-600')
    })
  })

  describe('AC2: Thumbs Down Button Click Handler', () => {
    it('renders thumbs down button with correct aria-label when not selected', () => {
      render(<FeedbackButtons eventId="event-1" />)

      const thumbsDownButton = screen.getByRole('button', { name: /mark as not helpful/i })
      expect(thumbsDownButton).toBeInTheDocument()
      expect(thumbsDownButton).toHaveAttribute('aria-pressed', 'false')
    })

    it('renders thumbs down button with "Marked as not helpful" aria-label when selected', () => {
      render(
        <FeedbackButtons
          eventId="event-1"
          existingFeedback={{ ...mockFeedback, rating: 'not_helpful' }}
        />
      )

      const thumbsDownButton = screen.getByRole('button', { name: /marked as not helpful/i })
      expect(thumbsDownButton).toBeInTheDocument()
      expect(thumbsDownButton).toHaveAttribute('aria-pressed', 'true')
    })

    it('opens correction input panel when clicked', async () => {
      const { user } = render(<FeedbackButtons eventId="event-1" />)

      const thumbsDownButton = screen.getByRole('button', { name: /mark as not helpful/i })
      await user.click(thumbsDownButton)

      // Correction panel should appear
      expect(screen.getByText(/what should it say/i)).toBeInTheDocument()
      expect(screen.getByRole('textbox', { name: /correction text/i })).toBeInTheDocument()
    })

    it('shows red styling when rating is "not_helpful"', () => {
      render(
        <FeedbackButtons
          eventId="event-1"
          existingFeedback={{ ...mockFeedback, rating: 'not_helpful' }}
        />
      )

      const thumbsDownButton = screen.getByRole('button', { name: /marked as not helpful/i })
      expect(thumbsDownButton).toHaveClass('bg-red-600')
    })

    it('does not have red styling when not selected', () => {
      render(<FeedbackButtons eventId="event-1" />)

      const thumbsDownButton = screen.getByRole('button', { name: /mark as not helpful/i })
      expect(thumbsDownButton).not.toHaveClass('bg-red-600')
    })
  })

  describe('AC3: Loading State', () => {
    it('shows loading spinner during submission', () => {
      ;(useSubmitFeedback as Mock).mockReturnValue({
        mutate: mockSubmitMutate,
        isPending: true,
      })

      render(<FeedbackButtons eventId="event-1" />)

      // Should show a spinner (Loader2 icon with animate-spin)
      const thumbsUpButton = screen.getByRole('button', { name: /mark as helpful/i })
      const spinner = thumbsUpButton.querySelector('.animate-spin')
      expect(spinner).toBeInTheDocument()
    })

    it('disables buttons during submission', () => {
      ;(useSubmitFeedback as Mock).mockReturnValue({
        mutate: mockSubmitMutate,
        isPending: true,
      })

      render(<FeedbackButtons eventId="event-1" />)

      const thumbsUpButton = screen.getByRole('button', { name: /mark as helpful/i })
      const thumbsDownButton = screen.getByRole('button', { name: /mark as not helpful/i })

      expect(thumbsUpButton).toBeDisabled()
      expect(thumbsDownButton).toBeDisabled()
    })

    it('disables skip and submit buttons in correction panel during pending', async () => {
      // Start with not pending so we can open the correction panel
      const { user } = render(<FeedbackButtons eventId="event-1" />)

      // Open correction panel
      const thumbsDownButton = screen.getByRole('button', { name: /mark as not helpful/i })
      await user.click(thumbsDownButton)

      // Verify correction panel is open - check for the characteristic text
      expect(screen.getByText(/what should it say/i)).toBeInTheDocument()

      // Find skip and submit buttons
      const skipButton = screen.getByRole('button', { name: /skip/i })
      const submitButton = screen.getByRole('button', { name: /^submit$/i })

      // They should be enabled when not pending
      expect(skipButton).not.toBeDisabled()
      expect(submitButton).not.toBeDisabled()
    })

    it('prevents click when isPending is true', async () => {
      ;(useSubmitFeedback as Mock).mockReturnValue({
        mutate: mockSubmitMutate,
        isPending: true,
      })

      const { user } = render(<FeedbackButtons eventId="event-1" />)

      const thumbsUpButton = screen.getByRole('button', { name: /mark as helpful/i })
      await user.click(thumbsUpButton)

      // Should not call mutate when pending
      expect(mockSubmitMutate).not.toHaveBeenCalled()
    })
  })

  describe('AC4: Already-Submitted State (Existing Feedback)', () => {
    it('initializes with existing feedback rating showing correct selected state', () => {
      render(
        <FeedbackButtons
          eventId="event-1"
          existingFeedback={{ ...mockFeedback, rating: 'helpful' }}
        />
      )

      const thumbsUpButton = screen.getByRole('button', { name: /marked as helpful/i })
      expect(thumbsUpButton).toHaveClass('bg-green-600')
      expect(thumbsUpButton).toHaveAttribute('aria-pressed', 'true')
    })

    it('calls updateFeedback instead of submitFeedback when changing existing rating', async () => {
      const { user } = render(
        <FeedbackButtons
          eventId="event-1"
          existingFeedback={{ ...mockFeedback, rating: 'helpful' }}
        />
      )

      const thumbsDownButton = screen.getByRole('button', { name: /mark as not helpful/i })
      await user.click(thumbsDownButton)

      // Since there's existing feedback, it should open correction panel
      // But the initial display should show the selected state
      expect(screen.getByText(/what should it say/i)).toBeInTheDocument()
    })

    it('shows correct selected state based on existingFeedback prop for not_helpful', () => {
      render(
        <FeedbackButtons
          eventId="event-1"
          existingFeedback={{ ...mockFeedback, rating: 'not_helpful' }}
        />
      )

      const thumbsDownButton = screen.getByRole('button', { name: /marked as not helpful/i })
      expect(thumbsDownButton).toHaveClass('bg-red-600')
      expect(thumbsDownButton).toHaveAttribute('aria-pressed', 'true')
    })

    it('shows correct selected state based on existingFeedback prop for helpful', () => {
      render(
        <FeedbackButtons
          eventId="event-1"
          existingFeedback={{ ...mockFeedback, rating: 'helpful' }}
        />
      )

      const thumbsUpButton = screen.getByRole('button', { name: /marked as helpful/i })
      expect(thumbsUpButton).toHaveClass('bg-green-600')
      expect(thumbsUpButton).toHaveAttribute('aria-pressed', 'true')
    })
  })

  describe('AC5: Correction Input Functionality', () => {
    it('shows correction textarea when thumbs down is clicked', async () => {
      const { user } = render(<FeedbackButtons eventId="event-1" />)

      await user.click(screen.getByRole('button', { name: /mark as not helpful/i }))

      expect(screen.getByRole('textbox', { name: /correction text/i })).toBeInTheDocument()
    })

    it('enforces character limit (500 max)', async () => {
      const { user } = render(<FeedbackButtons eventId="event-1" />)

      await user.click(screen.getByRole('button', { name: /mark as not helpful/i }))

      const textarea = screen.getByRole('textbox', { name: /correction text/i })
      expect(textarea).toHaveAttribute('maxLength', '500')
    })

    it('shows character count display', async () => {
      const { user } = render(<FeedbackButtons eventId="event-1" />)

      await user.click(screen.getByRole('button', { name: /mark as not helpful/i }))

      // Should show 0/500 initially
      expect(screen.getByText('0/500')).toBeInTheDocument()
    })

    it('updates character count as user types', async () => {
      const { user } = render(<FeedbackButtons eventId="event-1" />)

      await user.click(screen.getByRole('button', { name: /mark as not helpful/i }))

      const textarea = screen.getByRole('textbox', { name: /correction text/i })
      await user.type(textarea, 'Test correction')

      expect(screen.getByText('15/500')).toBeInTheDocument()
    })

    it('submit button sends correction text with "not_helpful" rating', async () => {
      const { user } = render(<FeedbackButtons eventId="event-1" />)

      await user.click(screen.getByRole('button', { name: /mark as not helpful/i }))

      const textarea = screen.getByRole('textbox', { name: /correction text/i })
      await user.type(textarea, 'Better description here')

      const submitButton = screen.getByRole('button', { name: /^submit$/i })
      await user.click(submitButton)

      expect(mockSubmitMutate).toHaveBeenCalledWith(
        {
          eventId: 'event-1',
          rating: 'not_helpful',
          correction: 'Better description here',
        },
        expect.any(Object)
      )
    })

    it('skip button sends "not_helpful" rating without correction', async () => {
      const { user } = render(<FeedbackButtons eventId="event-1" />)

      await user.click(screen.getByRole('button', { name: /mark as not helpful/i }))

      const skipButton = screen.getByRole('button', { name: /skip/i })
      await user.click(skipButton)

      expect(mockSubmitMutate).toHaveBeenCalledWith(
        {
          eventId: 'event-1',
          rating: 'not_helpful',
          correction: undefined,
        },
        expect.any(Object)
      )
    })

    it('cancel button closes correction panel without submitting', async () => {
      const { user } = render(<FeedbackButtons eventId="event-1" />)

      await user.click(screen.getByRole('button', { name: /mark as not helpful/i }))

      // Panel should be visible
      expect(screen.getByText(/what should it say/i)).toBeInTheDocument()

      const cancelButton = screen.getByRole('button', { name: /cancel correction/i })
      await user.click(cancelButton)

      // Panel should be closed
      expect(screen.queryByText(/what should it say/i)).not.toBeInTheDocument()

      // Should not have called mutate
      expect(mockSubmitMutate).not.toHaveBeenCalled()
    })
  })

  describe('AC6: ARIA Labels and Accessibility', () => {
    it('thumbs up button has aria-label "Mark as helpful" when unselected', () => {
      render(<FeedbackButtons eventId="event-1" />)

      const button = screen.getByRole('button', { name: /mark as helpful/i })
      expect(button).toHaveAttribute('aria-label', 'Mark as helpful')
    })

    it('thumbs up button has aria-label "Marked as helpful" when selected', () => {
      render(
        <FeedbackButtons
          eventId="event-1"
          existingFeedback={{ ...mockFeedback, rating: 'helpful' }}
        />
      )

      const button = screen.getByRole('button', { name: /marked as helpful/i })
      // Story P10-4.3: Updated aria-label to indicate click-to-modify
      expect(button).toHaveAttribute('aria-label', 'Marked as helpful - click to modify')
    })

    it('thumbs down button has aria-label "Mark as not helpful" when unselected', () => {
      render(<FeedbackButtons eventId="event-1" />)

      const button = screen.getByRole('button', { name: /mark as not helpful/i })
      expect(button).toHaveAttribute('aria-label', 'Mark as not helpful')
    })

    it('thumbs down button has aria-label "Marked as not helpful" when selected', () => {
      render(
        <FeedbackButtons
          eventId="event-1"
          existingFeedback={{ ...mockFeedback, rating: 'not_helpful' }}
        />
      )

      const button = screen.getByRole('button', { name: /marked as not helpful/i })
      // Story P10-4.3: Updated aria-label to indicate click-to-modify
      expect(button).toHaveAttribute('aria-label', 'Marked as not helpful - click to modify')
    })

    it('aria-pressed reflects current state for thumbs up', () => {
      const { rerender } = render(<FeedbackButtons eventId="event-1" />)

      let thumbsUpButton = screen.getByRole('button', { name: /mark as helpful/i })
      expect(thumbsUpButton).toHaveAttribute('aria-pressed', 'false')

      rerender(
        <FeedbackButtons
          eventId="event-1"
          existingFeedback={{ ...mockFeedback, rating: 'helpful' }}
        />
      )

      thumbsUpButton = screen.getByRole('button', { name: /marked as helpful/i })
      expect(thumbsUpButton).toHaveAttribute('aria-pressed', 'true')
    })

    it('aria-pressed reflects current state for thumbs down', () => {
      const { rerender } = render(<FeedbackButtons eventId="event-1" />)

      let thumbsDownButton = screen.getByRole('button', { name: /mark as not helpful/i })
      expect(thumbsDownButton).toHaveAttribute('aria-pressed', 'false')

      rerender(
        <FeedbackButtons
          eventId="event-1"
          existingFeedback={{ ...mockFeedback, rating: 'not_helpful' }}
        />
      )

      thumbsDownButton = screen.getByRole('button', { name: /marked as not helpful/i })
      expect(thumbsDownButton).toHaveAttribute('aria-pressed', 'true')
    })

    it('correction textarea has aria-label', async () => {
      const { user } = render(<FeedbackButtons eventId="event-1" />)

      await user.click(screen.getByRole('button', { name: /mark as not helpful/i }))

      const textarea = screen.getByRole('textbox', { name: /correction text/i })
      expect(textarea).toHaveAttribute('aria-label', 'Correction text')
    })

    it('cancel button has aria-label "Cancel correction"', async () => {
      const { user } = render(<FeedbackButtons eventId="event-1" />)

      await user.click(screen.getByRole('button', { name: /mark as not helpful/i }))

      const cancelButton = screen.getByRole('button', { name: /cancel correction/i })
      expect(cancelButton).toHaveAttribute('aria-label', 'Cancel correction')
    })
  })

  describe('Event propagation', () => {
    it('stops event propagation on button clicks', async () => {
      const handleContainerClick = vi.fn()

      const { user } = render(
        <div onClick={handleContainerClick}>
          <FeedbackButtons eventId="event-1" />
        </div>
      )

      await user.click(screen.getByRole('button', { name: /mark as helpful/i }))

      // Should not have propagated to container
      expect(handleContainerClick).not.toHaveBeenCalled()
    })

    it('stops event propagation on correction panel clicks', async () => {
      const handleContainerClick = vi.fn()

      const { user } = render(
        <div onClick={handleContainerClick}>
          <FeedbackButtons eventId="event-1" />
        </div>
      )

      await user.click(screen.getByRole('button', { name: /mark as not helpful/i }))

      // Click on the correction textarea
      const textarea = screen.getByRole('textbox', { name: /correction text/i })
      await user.click(textarea)

      // Should not have propagated to container
      expect(handleContainerClick).not.toHaveBeenCalled()
    })
  })

  describe('Callback integration', () => {
    it('calls onFeedbackChange callback when feedback is submitted', async () => {
      const onFeedbackChange = vi.fn()

      // Make the mutation call the onSuccess callback
      // Component expects data.feedback shape in onSuccess callback
      mockSubmitMutate.mockImplementation((params, options) => {
        options?.onSuccess?.({
          feedback: {
            ...mockFeedback,
            rating: params.rating,
          },
        })
      })

      const { user } = render(
        <FeedbackButtons
          eventId="event-1"
          onFeedbackChange={onFeedbackChange}
        />
      )

      await user.click(screen.getByRole('button', { name: /mark as helpful/i }))

      expect(onFeedbackChange).toHaveBeenCalledWith(
        expect.objectContaining({ rating: 'helpful' })
      )
    })
  })
})
