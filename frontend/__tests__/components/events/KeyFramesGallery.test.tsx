/**
 * KeyFramesGallery Component Tests
 *
 * Story P3-7.5: Tests for the key frames gallery component
 *
 * Demonstrates:
 * - Testing components with array props
 * - Testing conditional rendering (null when no frames)
 * - Testing click interactions (lightbox open)
 * - Testing timestamp formatting
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { KeyFramesGallery } from '@/components/events/KeyFramesGallery'

// Small 1x1 pixel JPEG as base64 for testing
const TEST_FRAME_BASE64 = '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCwAB//2Q=='

describe('KeyFramesGallery', () => {
  describe('rendering', () => {
    it('returns null when frames array is empty', () => {
      const { container } = render(
        <KeyFramesGallery frames={[]} timestamps={[]} />
      )

      expect(container).toBeEmptyDOMElement()
    })

    it('returns null when frames is undefined', () => {
      const { container } = render(
        // @ts-expect-error Testing undefined case
        <KeyFramesGallery frames={undefined} timestamps={[]} />
      )

      expect(container).toBeEmptyDOMElement()
    })

    it('renders section header with Film icon', () => {
      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64]}
          timestamps={[0.5]}
        />
      )

      expect(screen.getByText('Key Frames Used for Analysis')).toBeInTheDocument()
    })

    it('displays correct frame count in header', () => {
      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64, TEST_FRAME_BASE64, TEST_FRAME_BASE64]}
          timestamps={[0.5, 1.5, 2.5]}
        />
      )

      expect(screen.getByText('(3 frames)')).toBeInTheDocument()
    })

    it('displays singular "frame" for single frame', () => {
      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64]}
          timestamps={[0.5]}
        />
      )

      expect(screen.getByText('(1 frame)')).toBeInTheDocument()
    })

    it('renders frame thumbnails as images', () => {
      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64]}
          timestamps={[0.5]}
        />
      )

      const images = screen.getAllByRole('img')
      expect(images.length).toBeGreaterThan(0)
      expect(images[0]).toHaveAttribute('src', `data:image/jpeg;base64,${TEST_FRAME_BASE64}`)
    })

    it('displays frame numbers', () => {
      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64, TEST_FRAME_BASE64]}
          timestamps={[0.5, 1.5]}
        />
      )

      expect(screen.getByText('Frame 1')).toBeInTheDocument()
      expect(screen.getByText('Frame 2')).toBeInTheDocument()
    })
  })

  describe('timestamp formatting', () => {
    it('formats timestamp 0 as 0:00.00', () => {
      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64]}
          timestamps={[0]}
        />
      )

      expect(screen.getByText('0:00.00')).toBeInTheDocument()
    })

    it('formats timestamp with minutes correctly', () => {
      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64]}
          timestamps={[65.5]}
        />
      )

      // 65.5 seconds = 1:05.50
      expect(screen.getByText('1:05.50')).toBeInTheDocument()
    })

    it('formats timestamp with fractional seconds', () => {
      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64]}
          timestamps={[2.33]}
        />
      )

      // 2.33 seconds = 0:02.33
      expect(screen.getByText('0:02.33')).toBeInTheDocument()
    })

    it('handles missing timestamps gracefully', () => {
      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64, TEST_FRAME_BASE64]}
          timestamps={[0.5]} // Only one timestamp for two frames
        />
      )

      // Should not throw error, use 0 for missing timestamp
      expect(screen.getByText('0:00.50')).toBeInTheDocument()
      expect(screen.getByText('0:00.00')).toBeInTheDocument()
    })
  })

  describe('lightbox interaction', () => {
    it('opens lightbox when frame is clicked', async () => {
      const user = userEvent.setup()

      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64]}
          timestamps={[0.5]}
        />
      )

      // Click on the frame thumbnail button
      const frameButton = screen.getByRole('button', {
        name: /view frame 1/i
      })
      await user.click(frameButton)

      // Lightbox dialog should appear
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })
    })

    it('displays correct frame number in lightbox', async () => {
      const user = userEvent.setup()

      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64, TEST_FRAME_BASE64]}
          timestamps={[0.5, 1.5]}
        />
      )

      // Click on the second frame
      const frameButtons = screen.getAllByRole('button', { name: /view frame/i })
      await user.click(frameButtons[1])

      // Wait for dialog to open and check content
      await waitFor(() => {
        expect(screen.getByText(/Frame 2 of 2/i)).toBeInTheDocument()
      })
    })

    it('shows navigation arrows in lightbox for multiple frames', async () => {
      const user = userEvent.setup()

      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64, TEST_FRAME_BASE64, TEST_FRAME_BASE64]}
          timestamps={[0.5, 1.5, 2.5]}
        />
      )

      // Click on the first frame
      const frameButton = screen.getByRole('button', { name: /view frame 1/i })
      await user.click(frameButton)

      // Should have navigation buttons
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /previous frame/i })).toBeInTheDocument()
        expect(screen.getByRole('button', { name: /next frame/i })).toBeInTheDocument()
      })
    })

    it('closes lightbox when close button is clicked', async () => {
      const user = userEvent.setup()

      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64]}
          timestamps={[0.5]}
        />
      )

      // Open lightbox
      const frameButton = screen.getByRole('button', { name: /view frame 1/i })
      await user.click(frameButton)

      // Wait for dialog to open
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })

      // Click the Close button with text "Close" (not the X button)
      const closeButtons = screen.getAllByRole('button', { name: /close/i })
      // The last one should be our "Close" button with text
      const closeButton = closeButtons.find(btn => btn.textContent?.includes('Close'))
      expect(closeButton).toBeDefined()
      await user.click(closeButton!)

      // Dialog should close
      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      })
    })
  })

  describe('lightbox navigation', () => {
    it('navigates to next frame when next button is clicked', async () => {
      const user = userEvent.setup()

      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64, TEST_FRAME_BASE64]}
          timestamps={[0.5, 1.5]}
        />
      )

      // Open lightbox on first frame
      const frameButton = screen.getByRole('button', { name: /view frame 1/i })
      await user.click(frameButton)

      // Wait for dialog
      await waitFor(() => {
        expect(screen.getByText(/Frame 1 of 2/i)).toBeInTheDocument()
      })

      // Click next
      const nextButton = screen.getByRole('button', { name: /next frame/i })
      await user.click(nextButton)

      // Should show frame 2
      await waitFor(() => {
        expect(screen.getByText(/Frame 2 of 2/i)).toBeInTheDocument()
      })
    })

    it('navigates to previous frame when previous button is clicked', async () => {
      const user = userEvent.setup()

      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64, TEST_FRAME_BASE64]}
          timestamps={[0.5, 1.5]}
        />
      )

      // Open lightbox on second frame
      const frameButtons = screen.getAllByRole('button', { name: /view frame/i })
      await user.click(frameButtons[1])

      // Wait for dialog
      await waitFor(() => {
        expect(screen.getByText(/Frame 2 of 2/i)).toBeInTheDocument()
      })

      // Click previous
      const prevButton = screen.getByRole('button', { name: /previous frame/i })
      await user.click(prevButton)

      // Should show frame 1
      await waitFor(() => {
        expect(screen.getByText(/Frame 1 of 2/i)).toBeInTheDocument()
      })
    })

    it('disables previous button on first frame', async () => {
      const user = userEvent.setup()

      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64, TEST_FRAME_BASE64]}
          timestamps={[0.5, 1.5]}
        />
      )

      // Open lightbox on first frame
      const frameButton = screen.getByRole('button', { name: /view frame 1/i })
      await user.click(frameButton)

      // Previous button should be disabled
      await waitFor(() => {
        const prevButton = screen.getByRole('button', { name: /previous frame/i })
        expect(prevButton).toBeDisabled()
      })
    })

    it('disables next button on last frame', async () => {
      const user = userEvent.setup()

      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64, TEST_FRAME_BASE64]}
          timestamps={[0.5, 1.5]}
        />
      )

      // Open lightbox on last frame
      const frameButtons = screen.getAllByRole('button', { name: /view frame/i })
      await user.click(frameButtons[1])

      // Next button should be disabled
      await waitFor(() => {
        const nextButton = screen.getByRole('button', { name: /next frame/i })
        expect(nextButton).toBeDisabled()
      })
    })
  })

  describe('thumbnail strip in lightbox', () => {
    it('shows thumbnail strip for multiple frames', async () => {
      const user = userEvent.setup()

      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64, TEST_FRAME_BASE64, TEST_FRAME_BASE64]}
          timestamps={[0.5, 1.5, 2.5]}
        />
      )

      // Open lightbox
      const frameButton = screen.getByRole('button', { name: /view frame 1/i })
      await user.click(frameButton)

      // Wait for dialog
      await waitFor(() => {
        // Should have select frame buttons in thumbnail strip
        const selectButtons = screen.getAllByRole('button', { name: /select frame/i })
        expect(selectButtons.length).toBe(3)
      })
    })

    it('navigates to selected frame when thumbnail is clicked', async () => {
      const user = userEvent.setup()

      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64, TEST_FRAME_BASE64, TEST_FRAME_BASE64]}
          timestamps={[0.5, 1.5, 2.5]}
        />
      )

      // Open lightbox on first frame
      const frameButton = screen.getByRole('button', { name: /view frame 1/i })
      await user.click(frameButton)

      // Wait for dialog
      await waitFor(() => {
        expect(screen.getByText(/Frame 1 of 3/i)).toBeInTheDocument()
      })

      // Click on third thumbnail
      const selectButtons = screen.getAllByRole('button', { name: /select frame/i })
      await user.click(selectButtons[2])

      // Should show frame 3
      await waitFor(() => {
        expect(screen.getByText(/Frame 3 of 3/i)).toBeInTheDocument()
      })
    })
  })

  describe('accessibility', () => {
    it('frame buttons have accessible labels', () => {
      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64]}
          timestamps={[0.5]}
        />
      )

      const button = screen.getByRole('button', { name: /view frame 1 at 0:00.50/i })
      expect(button).toBeInTheDocument()
    })

    it('lightbox navigation buttons have accessible labels', async () => {
      const user = userEvent.setup()

      render(
        <KeyFramesGallery
          frames={[TEST_FRAME_BASE64, TEST_FRAME_BASE64]}
          timestamps={[0.5, 1.5]}
        />
      )

      // Open lightbox
      const frameButton = screen.getByRole('button', { name: /view frame 1/i })
      await user.click(frameButton)

      // Check button labels - dialog may have multiple close buttons (X and text)
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /previous frame/i })).toBeInTheDocument()
        expect(screen.getByRole('button', { name: /next frame/i })).toBeInTheDocument()
        // Check there's at least one close button (may be multiple)
        const closeButtons = screen.getAllByRole('button', { name: /close/i })
        expect(closeButtons.length).toBeGreaterThan(0)
      })
    })
  })
})
