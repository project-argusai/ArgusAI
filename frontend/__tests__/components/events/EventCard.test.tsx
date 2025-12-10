/**
 * EventCard Component Tests
 *
 * Tests for the main event card component displayed in timeline.
 *
 * Demonstrates:
 * - Testing memoized components
 * - Testing click handlers and event propagation
 * - Testing conditional rendering based on props
 * - Testing timestamp formatting
 * - Testing image error handling
 * - Testing expandable text content
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TooltipProvider } from '@/components/ui/tooltip'
import { EventCard } from '@/components/events/EventCard'
import type { IEvent } from '@/types/event'

// Wrapper to provide TooltipProvider context (needed for child components)
const renderWithProvider = (ui: React.ReactElement) => {
  return render(<TooltipProvider>{ui}</TooltipProvider>)
}

// Base mock event for tests
const createMockEvent = (overrides?: Partial<IEvent>): IEvent => ({
  id: 'evt-123',
  camera_id: 'cam-456',
  camera_name: 'Front Door',
  timestamp: '2024-01-15T10:30:00Z',
  description: 'A person was detected walking towards the front door.',
  thumbnail_base64: 'dGVzdGltYWdl', // base64 for "testimage"
  object_count: 1,
  detected_objects: ['person'],
  objects_detected: ['person'],
  confidence_score: 85,
  confidence: 85,
  source_type: 'protect',
  is_doorbell_ring: false,
  low_confidence: false,
  ...overrides,
})

describe('EventCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('rendering', () => {
    it('renders event card with camera name', () => {
      const event = createMockEvent()
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      expect(screen.getByText('Front Door')).toBeInTheDocument()
    })

    it('renders camera ID when camera name is not available', () => {
      const event = createMockEvent({ camera_name: undefined })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      // Should show truncated camera ID
      expect(screen.getByText(/Camera cam-456/)).toBeInTheDocument()
    })

    it('renders event description', () => {
      const event = createMockEvent()
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      expect(
        screen.getByText('A person was detected walking towards the front door.')
      ).toBeInTheDocument()
    })

    it('renders confidence score', () => {
      const event = createMockEvent({ confidence: 85 })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      expect(screen.getByText('85% confident')).toBeInTheDocument()
    })

    it('renders detected objects with icons', () => {
      const event = createMockEvent({ objects_detected: ['person', 'vehicle'] })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      expect(screen.getByText('Person')).toBeInTheDocument()
      expect(screen.getByText('Vehicle')).toBeInTheDocument()
    })

    it('renders source type badge for protect cameras', () => {
      const event = createMockEvent({ source_type: 'protect' })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      // SourceTypeBadge shows "Protect" for protect source
      expect(screen.getByText('Protect')).toBeInTheDocument()
    })

    it('renders source type badge for rtsp cameras', () => {
      const event = createMockEvent({ source_type: 'rtsp' })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      expect(screen.getByText('RTSP')).toBeInTheDocument()
    })

    it('renders relative timestamp', () => {
      const event = createMockEvent()
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      // formatDistanceToNow will show something like "X months ago" or similar
      // Just check that there's a time element
      const timeElement = screen.getByRole('time')
      expect(timeElement).toBeInTheDocument()
    })

    it('sets data-event-id attribute for scrolling support', () => {
      const event = createMockEvent()
      const onClick = vi.fn()

      const { container } = renderWithProvider(
        <EventCard event={event} onClick={onClick} />
      )

      const card = container.querySelector('[data-event-id="evt-123"]')
      expect(card).toBeInTheDocument()
    })
  })

  describe('thumbnail handling', () => {
    it('renders thumbnail from base64 data', () => {
      const event = createMockEvent({ thumbnail_base64: 'abc123' })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      const img = screen.getByRole('img', { name: 'Event thumbnail' })
      expect(img).toHaveAttribute('src', 'data:image/jpeg;base64,abc123')
    })

    it('renders thumbnail from path when base64 not available', () => {
      const event = createMockEvent({
        thumbnail_base64: null,
        thumbnail_path: '/api/v1/thumbnails/2024-01/test.jpg',
      })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      const img = screen.getByRole('img', { name: 'Event thumbnail' })
      expect(img).toHaveAttribute(
        'src',
        'http://localhost:8000/api/v1/thumbnails/2024-01/test.jpg'
      )
    })

    it('shows placeholder when no thumbnail available', () => {
      const event = createMockEvent({
        thumbnail_base64: null,
        thumbnail_path: undefined,
      })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      expect(screen.getByText('No thumbnail available')).toBeInTheDocument()
    })

    it('shows placeholder on image error', async () => {
      const user = userEvent.setup()
      const event = createMockEvent({ thumbnail_base64: 'invalid' })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      const img = screen.getByRole('img', { name: 'Event thumbnail' })

      // Simulate image error using fireEvent which handles act() properly
      const { fireEvent } = await import('@testing-library/react')
      fireEvent.error(img)

      expect(screen.getByText('No thumbnail available')).toBeInTheDocument()
    })
  })

  describe('description truncation', () => {
    it('truncates long descriptions', () => {
      const longDescription =
        'This is a very long description that exceeds the maximum length. '.repeat(
          5
        )
      const event = createMockEvent({ description: longDescription })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      // Should show truncated text with ellipsis
      expect(screen.getByText(/\.\.\./)).toBeInTheDocument()
      expect(screen.getByText('Read more')).toBeInTheDocument()
    })

    it('expands description when Read more is clicked', async () => {
      const user = userEvent.setup()
      const longDescription =
        'This is a very long description that exceeds the maximum length of 150 characters and needs to be truncated. More content here to ensure it is long enough.'.repeat(
          2
        )
      const event = createMockEvent({ description: longDescription })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      const readMoreButton = screen.getByText('Read more')
      await user.click(readMoreButton)

      // Should now show full description and "Show less" button
      expect(screen.getByText('Show less')).toBeInTheDocument()
      // onClick should NOT have been called (event propagation stopped)
      expect(onClick).not.toHaveBeenCalled()
    })

    it('collapses description when Show less is clicked', async () => {
      const user = userEvent.setup()
      const longDescription =
        'This is a very long description that exceeds the maximum length of 150 characters and needs to be truncated. More content here to ensure it is long enough.'.repeat(
          2
        )
      const event = createMockEvent({ description: longDescription })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      // Expand
      await user.click(screen.getByText('Read more'))
      // Collapse
      await user.click(screen.getByText('Show less'))

      expect(screen.getByText('Read more')).toBeInTheDocument()
    })

    it('does not show expand button for short descriptions', () => {
      const event = createMockEvent({ description: 'Short description.' })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      expect(screen.queryByText('Read more')).not.toBeInTheDocument()
    })
  })

  describe('click handling', () => {
    it('calls onClick when card is clicked', async () => {
      const user = userEvent.setup()
      const event = createMockEvent()
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      // Click on the card (description area)
      await user.click(screen.getByText(event.description))

      expect(onClick).toHaveBeenCalledTimes(1)
    })
  })

  describe('confidence styling', () => {
    it('applies green styling for high confidence (>=80)', () => {
      const event = createMockEvent({ confidence: 85 })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      const confidenceBadge = screen.getByText('85% confident')
      expect(confidenceBadge).toHaveClass('bg-green-50')
      expect(confidenceBadge).toHaveClass('text-green-600')
    })

    it('applies yellow styling for medium confidence (50-79)', () => {
      const event = createMockEvent({ confidence: 70 })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      const confidenceBadge = screen.getByText('70% confident')
      expect(confidenceBadge).toHaveClass('bg-yellow-50')
      expect(confidenceBadge).toHaveClass('text-yellow-600')
    })

    it('applies red styling for low confidence (<50)', () => {
      const event = createMockEvent({ confidence: 45 })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      const confidenceBadge = screen.getByText('45% confident')
      expect(confidenceBadge).toHaveClass('bg-red-50')
      expect(confidenceBadge).toHaveClass('text-red-600')
    })
  })

  describe('smart detection badge', () => {
    it('renders SmartDetectionBadge when smart_detection_type is present', () => {
      const event = createMockEvent({
        smart_detection_type: 'vehicle',
        objects_detected: [], // Clear objects to avoid confusion
      })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      // SmartDetectionBadge renders vehicle with purple styling (each type has distinct colors)
      const badge = screen.getByText('Vehicle')
      expect(badge.closest('span')).toHaveClass('bg-purple-100')
    })

    it('does not render SmartDetectionBadge when no smart detection', () => {
      const event = createMockEvent({
        smart_detection_type: undefined,
        objects_detected: ['person'],
      })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      // The Person badge should be gray (detected object), not blue (smart detection)
      const personBadge = screen.getByText('Person')
      expect(personBadge.closest('span')).toHaveClass('bg-gray-100')
    })
  })

  describe('correlation indicator', () => {
    it('renders CorrelationIndicator when correlated events exist', () => {
      const event = createMockEvent({
        correlated_events: [
          { id: 'evt-789', camera_name: 'Back Yard' },
          { id: 'evt-790', camera_name: 'Side Gate' },
        ],
      })
      const onClick = vi.fn()
      const onCorrelatedEventClick = vi.fn()

      renderWithProvider(
        <EventCard
          event={event}
          onClick={onClick}
          onCorrelatedEventClick={onCorrelatedEventClick}
        />
      )

      // CorrelationIndicator shows "Also captured by:" with camera names
      expect(screen.getByText('Also captured by:')).toBeInTheDocument()
      expect(screen.getByText('Back Yard')).toBeInTheDocument()
      expect(screen.getByText('Side Gate')).toBeInTheDocument()
    })

    it('does not render CorrelationIndicator without onCorrelatedEventClick', () => {
      const event = createMockEvent({
        correlated_events: [{ id: 'evt-789', camera_name: 'Back Yard' }],
      })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      // CorrelationIndicator should not be visible without callback
      expect(screen.queryByText('Also captured by:')).not.toBeInTheDocument()
    })

    it('applies blue left border when event has correlations', () => {
      const event = createMockEvent({
        correlated_events: [{ id: 'evt-789', camera_name: 'Back Yard' }],
      })
      const onClick = vi.fn()
      const onCorrelatedEventClick = vi.fn()

      const { container } = renderWithProvider(
        <EventCard
          event={event}
          onClick={onClick}
          onCorrelatedEventClick={onCorrelatedEventClick}
        />
      )

      const card = container.querySelector('[data-event-id="evt-123"]')
      expect(card).toHaveClass('border-l-4')
      expect(card).toHaveClass('border-l-blue-400')
    })
  })

  describe('highlight state', () => {
    it('applies highlight styling when isHighlighted is true', () => {
      const event = createMockEvent()
      const onClick = vi.fn()

      const { container } = renderWithProvider(
        <EventCard event={event} onClick={onClick} isHighlighted={true} />
      )

      const card = container.querySelector('[data-event-id="evt-123"]')
      expect(card).toHaveClass('ring-2')
      expect(card).toHaveClass('ring-blue-500')
      expect(card).toHaveClass('animate-pulse')
    })

    it('does not apply highlight styling by default', () => {
      const event = createMockEvent()
      const onClick = vi.fn()

      const { container } = renderWithProvider(
        <EventCard event={event} onClick={onClick} />
      )

      const card = container.querySelector('[data-event-id="evt-123"]')
      expect(card).not.toHaveClass('ring-2')
      expect(card).not.toHaveClass('animate-pulse')
    })
  })

  describe('analysis mode and provider badges', () => {
    it('renders AnalysisModeBadge when analysis_mode is present', () => {
      const event = createMockEvent({ analysis_mode: 'multi_frame' })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      // AnalysisModeBadge shows "MF" for multi_frame
      expect(screen.getByText('MF')).toBeInTheDocument()
    })

    it('renders AIProviderBadge when provider_used is present', () => {
      const event = createMockEvent({ provider_used: 'openai' })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      // AIProviderBadge shows label "OpenAI"
      expect(screen.getByText('OpenAI')).toBeInTheDocument()
    })
  })

  describe('confidence indicator and re-analyze', () => {
    it('renders ConfidenceIndicator with AI confidence data', () => {
      const event = createMockEvent({
        ai_confidence: 75,
        low_confidence: false,
      })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      // ConfidenceIndicator should be rendered
      // The exact content depends on the component implementation
      expect(screen.getByText('75%')).toBeInTheDocument()
    })

    it('renders ReanalyzedIndicator when event was reanalyzed', () => {
      const event = createMockEvent({
        reanalyzed_at: '2024-01-15T11:00:00Z',
      })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      // ReanalyzedIndicator shows "Re-analyzed" text
      expect(screen.getByText('Re-analyzed')).toBeInTheDocument()
    })
  })

  describe('object icons', () => {
    it('renders correct icon for person', () => {
      const event = createMockEvent({ objects_detected: ['person'] })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      const personBadge = screen.getByText('Person').closest('span')
      expect(personBadge).toHaveTextContent('👤')
    })

    it('renders correct icon for vehicle', () => {
      const event = createMockEvent({ objects_detected: ['vehicle'] })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      const vehicleBadge = screen.getByText('Vehicle').closest('span')
      expect(vehicleBadge).toHaveTextContent('🚗')
    })

    it('renders correct icon for animal', () => {
      const event = createMockEvent({ objects_detected: ['animal'] })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      const animalBadge = screen.getByText('Animal').closest('span')
      expect(animalBadge).toHaveTextContent('🐾')
    })

    it('renders correct icon for package', () => {
      const event = createMockEvent({ objects_detected: ['package'] })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      const packageBadge = screen.getByText('Package').closest('span')
      expect(packageBadge).toHaveTextContent('📦')
    })

    it('renders unknown icon for unrecognized objects', () => {
      const event = createMockEvent({ objects_detected: ['robot'] })
      const onClick = vi.fn()

      renderWithProvider(<EventCard event={event} onClick={onClick} />)

      const robotBadge = screen.getByText('Robot').closest('span')
      expect(robotBadge).toHaveTextContent('❓')
    })
  })
})
