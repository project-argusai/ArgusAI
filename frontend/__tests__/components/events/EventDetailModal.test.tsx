/**
 * EventDetailModal Component Tests
 *
 * Tests for the event detail modal with navigation and delete functionality.
 *
 * Demonstrates:
 * - Testing dialog/modal components
 * - Testing navigation between events
 * - Testing keyboard navigation
 * - Testing delete confirmation flow
 * - Testing image error handling
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { EventDetailModal } from '@/components/events/EventDetailModal'
import { apiClient } from '@/lib/api-client'
import type { IEvent } from '@/types/event'
import React from 'react'

// Mock the API client
vi.mock('@/lib/api-client', () => ({
  apiClient: {
    events: {
      delete: vi.fn(),
    },
  },
}))

// Mock sonner toast
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

const mockApiClient = apiClient as {
  events: {
    delete: ReturnType<typeof vi.fn>
  }
}

// Base mock event for tests
const createMockEvent = (overrides?: Partial<IEvent>): IEvent => ({
  id: 'evt-123',
  camera_id: 'cam-456-abcd-efgh',
  camera_name: 'Front Door',
  timestamp: '2024-01-15T10:30:00Z',
  description: 'A person was detected walking towards the front door.',
  thumbnail_base64: 'dGVzdGltYWdl', // base64 for "testimage"
  thumbnail_path: null,
  object_count: 1,
  detected_objects: ['person'],
  objects_detected: ['person'],
  confidence_score: 85,
  confidence: 85,
  source_type: 'protect',
  is_doorbell_ring: false,
  low_confidence: false,
  alert_triggered: false,
  created_at: '2024-01-15T10:30:00Z',
  ...overrides,
})

// Create multiple events for navigation testing
const createMockEvents = (): IEvent[] => [
  createMockEvent({ id: 'evt-1', description: 'First event' }),
  createMockEvent({ id: 'evt-2', description: 'Second event' }),
  createMockEvent({ id: 'evt-3', description: 'Third event' }),
]

describe('EventDetailModal', () => {
  let queryClient: QueryClient

  // Create wrapper with QueryClientProvider
  const createWrapper = () => {
    return function Wrapper({ children }: { children: React.ReactNode }) {
      return (
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      )
    }
  }

  const renderModal = (
    event: IEvent | null,
    props: Partial<React.ComponentProps<typeof EventDetailModal>> = {}
  ) => {
    return render(
      <EventDetailModal
        event={event}
        open={true}
        onClose={vi.fn()}
        {...props}
      />,
      { wrapper: createWrapper() }
    )
  }

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
    vi.clearAllMocks()
  })

  describe('rendering', () => {
    it('renders nothing when event is null', () => {
      renderModal(null)
      expect(screen.queryByText('Event Details')).not.toBeInTheDocument()
    })

    it('renders nothing when open is false', () => {
      const event = createMockEvent()
      render(
        <EventDetailModal event={event} open={false} onClose={vi.fn()} />,
        { wrapper: createWrapper() }
      )
      expect(screen.queryByText('Event Details')).not.toBeInTheDocument()
    })

    it('renders modal title when open with event', () => {
      const event = createMockEvent()
      renderModal(event)
      expect(screen.getByText('Event Details')).toBeInTheDocument()
    })

    it('renders event description', () => {
      const event = createMockEvent({ description: 'Test description' })
      renderModal(event)
      expect(screen.getByText('Test description')).toBeInTheDocument()
    })

    it('renders camera ID (truncated)', () => {
      const event = createMockEvent({ camera_id: 'cam-456-abcd-efgh' })
      renderModal(event)
      expect(screen.getByText('cam-456-')).toBeInTheDocument()
    })

    it('renders timestamp', () => {
      const event = createMockEvent()
      renderModal(event)
      // Should have a time element with the timestamp
      const timeElement = screen.getByRole('time')
      expect(timeElement).toBeInTheDocument()
    })

    it('renders detected objects', () => {
      const event = createMockEvent({ objects_detected: ['person', 'vehicle'] })
      renderModal(event)
      expect(screen.getByText('Person')).toBeInTheDocument()
      expect(screen.getByText('Vehicle')).toBeInTheDocument()
    })

    it('renders confidence score', () => {
      const event = createMockEvent({ confidence: 85 })
      renderModal(event)
      expect(screen.getByText('85%')).toBeInTheDocument()
      expect(screen.getByText('(high)')).toBeInTheDocument()
    })
  })

  describe('image handling', () => {
    it('displays image from base64 thumbnail', () => {
      const event = createMockEvent({ thumbnail_base64: 'abc123' })
      renderModal(event)
      const img = screen.getByRole('img', { name: 'Event image' })
      expect(img).toHaveAttribute('src')
      // Next.js Image may modify src, check it contains the base64 indicator
    })

    it('displays image from thumbnail path when no base64', () => {
      const event = createMockEvent({
        thumbnail_base64: null,
        thumbnail_path: '/api/v1/thumbnails/test.jpg',
      })
      renderModal(event)
      const img = screen.getByRole('img', { name: 'Event image' })
      expect(img).toBeInTheDocument()
    })

    it('shows placeholder when no image available', () => {
      const event = createMockEvent({
        thumbnail_base64: null,
        thumbnail_path: null,
      })
      renderModal(event)
      expect(screen.getByText('No image available')).toBeInTheDocument()
    })
  })

  describe('navigation', () => {
    it('shows navigation controls when multiple events', () => {
      const events = createMockEvents()
      renderModal(events[1], { allEvents: events })

      expect(screen.getByLabelText('Previous event')).toBeInTheDocument()
      expect(screen.getByLabelText('Next event')).toBeInTheDocument()
      expect(screen.getByText('2 / 3')).toBeInTheDocument()
    })

    it('does not show navigation controls for single event', () => {
      const event = createMockEvent()
      renderModal(event, { allEvents: [event] })

      expect(screen.queryByLabelText('Previous event')).not.toBeInTheDocument()
      expect(screen.queryByLabelText('Next event')).not.toBeInTheDocument()
    })

    it('disables previous button on first event', () => {
      const events = createMockEvents()
      renderModal(events[0], { allEvents: events })

      expect(screen.getByLabelText('Previous event')).toBeDisabled()
      expect(screen.getByLabelText('Next event')).not.toBeDisabled()
    })

    it('disables next button on last event', () => {
      const events = createMockEvents()
      renderModal(events[2], { allEvents: events })

      expect(screen.getByLabelText('Previous event')).not.toBeDisabled()
      expect(screen.getByLabelText('Next event')).toBeDisabled()
    })

    it('calls onNavigate when clicking next', async () => {
      const user = userEvent.setup()
      const events = createMockEvents()
      const onNavigate = vi.fn()

      renderModal(events[0], { allEvents: events, onNavigate })

      await user.click(screen.getByLabelText('Next event'))

      expect(onNavigate).toHaveBeenCalledWith(events[1])
    })

    it('calls onNavigate when clicking previous', async () => {
      const user = userEvent.setup()
      const events = createMockEvents()
      const onNavigate = vi.fn()

      renderModal(events[1], { allEvents: events, onNavigate })

      await user.click(screen.getByLabelText('Previous event'))

      expect(onNavigate).toHaveBeenCalledWith(events[0])
    })
  })

  describe('close functionality', () => {
    it('calls onClose when Close button clicked', async () => {
      const user = userEvent.setup()
      const event = createMockEvent()
      const onClose = vi.fn()

      render(
        <EventDetailModal event={event} open={true} onClose={onClose} />,
        { wrapper: createWrapper() }
      )

      // Find the Close button in the footer (the one with X icon and "Close" text)
      const closeButtons = screen.getAllByRole('button', { name: /close/i })
      // The footer Close button is the last one (after the dialog's internal close)
      const footerCloseButton = closeButtons.find(btn => btn.textContent?.includes('Close'))
      expect(footerCloseButton).toBeDefined()
      await user.click(footerCloseButton!)

      expect(onClose).toHaveBeenCalled()
    })
  })

  describe('delete functionality', () => {
    it('shows delete confirmation dialog when Delete button clicked', async () => {
      const user = userEvent.setup()
      const event = createMockEvent()

      renderModal(event)

      await user.click(screen.getByText('Delete Event'))

      expect(screen.getByText('Delete Event?')).toBeInTheDocument()
      expect(screen.getByText(/This action cannot be undone/)).toBeInTheDocument()
    })

    it('cancels delete when Cancel clicked in confirmation', async () => {
      const user = userEvent.setup()
      const event = createMockEvent()

      renderModal(event)

      await user.click(screen.getByText('Delete Event'))
      await user.click(screen.getByText('Cancel'))

      // Confirmation dialog should be closed
      expect(screen.queryByText('Delete Event?')).not.toBeInTheDocument()
    })

    it('calls delete API when confirmed', async () => {
      const user = userEvent.setup()
      const event = createMockEvent()
      const onClose = vi.fn()
      mockApiClient.events.delete.mockResolvedValueOnce(undefined)

      render(
        <EventDetailModal event={event} open={true} onClose={onClose} />,
        { wrapper: createWrapper() }
      )

      await user.click(screen.getByText('Delete Event'))

      // Click Delete in the confirmation dialog
      const confirmButton = screen.getByRole('button', { name: 'Delete' })
      await user.click(confirmButton)

      await waitFor(() => {
        expect(mockApiClient.events.delete).toHaveBeenCalledWith('evt-123')
      })
    })

    it('closes modal after successful delete', async () => {
      const user = userEvent.setup()
      const event = createMockEvent()
      const onClose = vi.fn()
      mockApiClient.events.delete.mockResolvedValueOnce(undefined)

      render(
        <EventDetailModal event={event} open={true} onClose={onClose} />,
        { wrapper: createWrapper() }
      )

      await user.click(screen.getByText('Delete Event'))
      const confirmButton = screen.getByRole('button', { name: 'Delete' })
      await user.click(confirmButton)

      await waitFor(() => {
        expect(onClose).toHaveBeenCalled()
      })
    })
  })

  describe('AI provider display', () => {
    it('shows OpenAI provider details when provider_used is openai', () => {
      const event = createMockEvent({ provider_used: 'openai' })
      renderModal(event)

      expect(screen.getByText('AI Provider')).toBeInTheDocument()
      expect(screen.getByText('OpenAI GPT-4o mini')).toBeInTheDocument()
    })

    it('shows Grok provider details when provider_used is grok', () => {
      const event = createMockEvent({ provider_used: 'grok' })
      renderModal(event)

      expect(screen.getByText('xAI Grok 2 Vision')).toBeInTheDocument()
    })

    it('shows Claude provider details when provider_used is claude', () => {
      const event = createMockEvent({ provider_used: 'claude' })
      renderModal(event)

      expect(screen.getByText('Anthropic Claude 3 Haiku')).toBeInTheDocument()
    })

    it('shows Gemini provider details when provider_used is gemini', () => {
      const event = createMockEvent({ provider_used: 'gemini' })
      renderModal(event)

      expect(screen.getByText('Google Gemini 2.0 Flash')).toBeInTheDocument()
    })

    it('does not show provider section when provider_used is null', () => {
      const event = createMockEvent({ provider_used: null })
      renderModal(event)

      expect(screen.queryByText('AI Provider')).not.toBeInTheDocument()
    })
  })

  describe('alert status', () => {
    it('shows alert status when alert_triggered is true', () => {
      const event = createMockEvent({ alert_triggered: true })
      renderModal(event)

      expect(screen.getByText('Alert Status')).toBeInTheDocument()
      expect(screen.getByText('Alert was triggered for this event')).toBeInTheDocument()
    })

    it('does not show alert status when alert_triggered is false', () => {
      const event = createMockEvent({ alert_triggered: false })
      renderModal(event)

      expect(screen.queryByText('Alert Status')).not.toBeInTheDocument()
    })
  })

  describe('related events', () => {
    it('shows related events section when correlated_events exist', () => {
      const event = createMockEvent({
        correlated_events: [
          { id: 'evt-rel-1', camera_name: 'Back Yard', thumbnail_url: null, timestamp: '2024-01-15T10:30:05Z' },
          { id: 'evt-rel-2', camera_name: 'Side Gate', thumbnail_url: null, timestamp: '2024-01-15T10:30:10Z' },
        ],
      })
      renderModal(event)

      expect(screen.getByText('Related Events')).toBeInTheDocument()
      expect(screen.getByText('(2 other cameras)')).toBeInTheDocument()
      expect(screen.getByText('Back Yard')).toBeInTheDocument()
      expect(screen.getByText('Side Gate')).toBeInTheDocument()
    })

    it('does not show related events when none exist', () => {
      const event = createMockEvent({ correlated_events: undefined })
      renderModal(event)

      expect(screen.queryByText('Related Events')).not.toBeInTheDocument()
    })

    it('shows singular text for single related event', () => {
      const event = createMockEvent({
        correlated_events: [
          { id: 'evt-rel-1', camera_name: 'Back Yard', thumbnail_url: null, timestamp: '2024-01-15T10:30:05Z' },
        ],
      })
      renderModal(event)

      expect(screen.getByText('(1 other camera)')).toBeInTheDocument()
    })
  })

  describe('key frames gallery', () => {
    it('shows key frames gallery when key_frames_base64 exists', () => {
      const event = createMockEvent({
        key_frames_base64: ['frame1base64', 'frame2base64', 'frame3base64'],
        frame_timestamps: [0.5, 1.5, 2.5],
      })
      renderModal(event)

      // KeyFramesGallery shows "Key Frames Used for Analysis" as title
      expect(screen.getByText('Key Frames Used for Analysis')).toBeInTheDocument()
      expect(screen.getByText('(3 frames)')).toBeInTheDocument()
    })

    it('does not show key frames gallery when no frames', () => {
      const event = createMockEvent({
        key_frames_base64: [],
        frame_timestamps: [],
      })
      renderModal(event)

      expect(screen.queryByText('Key Frames Used for Analysis')).not.toBeInTheDocument()
    })
  })

  describe('confidence styling', () => {
    it('shows high confidence level', () => {
      const event = createMockEvent({ confidence: 85 })
      renderModal(event)
      expect(screen.getByText('(high)')).toBeInTheDocument()
    })

    it('shows medium confidence level', () => {
      const event = createMockEvent({ confidence: 65 })
      renderModal(event)
      expect(screen.getByText('(medium)')).toBeInTheDocument()
    })

    it('shows low confidence level', () => {
      const event = createMockEvent({ confidence: 35 })
      renderModal(event)
      expect(screen.getByText('(low)')).toBeInTheDocument()
    })
  })
})
