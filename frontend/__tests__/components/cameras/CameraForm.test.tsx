/**
 * CameraForm Component Tests
 *
 * Tests for the camera creation/edit form with validation and conditional fields.
 *
 * Demonstrates:
 * - Testing React Hook Form with Zod validation
 * - Testing conditional field rendering (RTSP vs USB)
 * - Testing form submission
 * - Testing API integration (test connection)
 * - Testing slider inputs
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CameraForm } from '@/components/cameras/CameraForm'
import { apiClient, ApiError } from '@/lib/api-client'
import type { ICamera, ICameraTestResponse } from '@/types/camera'

// Mock DOM methods for Radix UI Select
beforeEach(() => {
  Element.prototype.hasPointerCapture = vi.fn(() => false)
  Element.prototype.setPointerCapture = vi.fn()
  Element.prototype.releasePointerCapture = vi.fn()
  Element.prototype.scrollIntoView = vi.fn()
})

// Mock the API client
vi.mock('@/lib/api-client', () => ({
  apiClient: {
    cameras: {
      testConnection: vi.fn(),
    },
  },
  ApiError: class ApiError extends Error {
    constructor(message: string) {
      super(message)
      this.name = 'ApiError'
    }
  },
}))

// Mock child components that have complex dependencies
vi.mock('@/components/cameras/MotionSettingsSection', () => ({
  MotionSettingsSection: () => (
    <div data-testid="motion-settings-section">Motion Settings Section</div>
  ),
}))

vi.mock('@/components/cameras/DetectionZoneDrawer', () => ({
  DetectionZoneDrawer: ({ onZoneComplete, onCancel }: { onZoneComplete: (vertices: Array<{x: number, y: number}>) => void, onCancel: () => void }) => (
    <div data-testid="detection-zone-drawer">
      <button
        type="button"
        onClick={() => onZoneComplete([{ x: 0.1, y: 0.1 }, { x: 0.9, y: 0.1 }, { x: 0.9, y: 0.9 }])}
      >
        Complete Zone
      </button>
      <button type="button" onClick={onCancel}>Cancel Drawing</button>
    </div>
  ),
}))

vi.mock('@/components/cameras/DetectionZoneList', () => ({
  DetectionZoneList: ({ zones, onZoneUpdate, onZoneDelete }: {
    zones: Array<{ id: string; name: string }>
    onZoneUpdate: (id: string, updates: object) => void
    onZoneDelete: (id: string) => void
  }) => (
    <div data-testid="detection-zone-list">
      {zones.map((zone) => (
        <div key={zone.id} data-testid={`zone-${zone.id}`}>
          <span>{zone.name}</span>
          <button type="button" onClick={() => onZoneDelete(zone.id)}>Delete {zone.name}</button>
          <button type="button" onClick={() => onZoneUpdate(zone.id, { name: 'Updated Zone' })}>
            Update {zone.name}
          </button>
        </div>
      ))}
    </div>
  ),
}))

vi.mock('@/components/cameras/ZonePresetTemplates', () => ({
  ZonePresetTemplates: ({ onTemplateSelect }: { onTemplateSelect: (vertices: Array<{x: number, y: number}>) => void }) => (
    <div data-testid="zone-preset-templates">
      <button
        type="button"
        onClick={() => onTemplateSelect([{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 1, y: 1 }, { x: 0, y: 1 }])}
      >
        Full Frame Template
      </button>
    </div>
  ),
}))

vi.mock('@/components/cameras/DetectionScheduleEditor', () => ({
  DetectionScheduleEditor: () => (
    <div data-testid="detection-schedule-editor">Detection Schedule Editor</div>
  ),
}))

vi.mock('@/components/cameras/AnalysisModeSelector', () => ({
  AnalysisModeSelector: ({ sourceType }: { sourceType: string }) => (
    <div data-testid="analysis-mode-selector" data-source-type={sourceType}>
      Analysis Mode Selector
    </div>
  ),
}))

const mockApiClient = apiClient as {
  cameras: {
    testConnection: ReturnType<typeof vi.fn>
  }
}

// Base mock camera for edit mode tests
const createMockCamera = (overrides?: Partial<ICamera>): ICamera => ({
  id: 'cam-123',
  name: 'Test Camera',
  type: 'rtsp',
  rtsp_url: 'rtsp://192.168.1.100:554/stream',
  username: 'admin',
  frame_rate: 10,
  is_enabled: true,
  motion_enabled: true,
  motion_sensitivity: 'medium',
  motion_cooldown: 30,
  motion_algorithm: 'mog2',
  detection_zones: [],
  detection_schedule: {
    enabled: false,
    start_time: '09:00',
    end_time: '17:00',
    days: [0, 1, 2, 3, 4],
  },
  analysis_mode: 'single_frame',
  source_type: 'rtsp',
  created_at: '2024-01-15T10:00:00Z',
  updated_at: '2024-01-15T10:00:00Z',
  ...overrides,
})

describe('CameraForm', () => {
  const mockOnSubmit = vi.fn()
  const mockOnCancel = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('rendering - create mode', () => {
    it('renders form with default values in create mode', () => {
      render(<CameraForm onSubmit={mockOnSubmit} />)

      expect(screen.getByLabelText(/camera name/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/camera type/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /save camera/i })).toBeInTheDocument()
    })

    it('shows RTSP fields by default', () => {
      render(<CameraForm onSubmit={mockOnSubmit} />)

      expect(screen.getByLabelText(/rtsp url/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/username/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
    })

    it('shows test connection for RTSP cameras in create mode', () => {
      render(<CameraForm onSubmit={mockOnSubmit} />)

      // Test connection is now shown for RTSP cameras in create mode
      // so users can test their URL before saving
      expect(screen.getByText(/test connection/i)).toBeInTheDocument()
      // Button is disabled until RTSP URL is entered
      expect(screen.getByRole('button', { name: /^test$/i })).toBeDisabled()
    })

    it('shows cancel button when onCancel is provided', () => {
      render(<CameraForm onSubmit={mockOnSubmit} onCancel={mockOnCancel} />)

      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
    })

    it('does not show cancel button when onCancel is not provided', () => {
      render(<CameraForm onSubmit={mockOnSubmit} />)

      expect(screen.queryByRole('button', { name: /cancel/i })).not.toBeInTheDocument()
    })
  })

  describe('rendering - edit mode', () => {
    it('renders form with initial data in edit mode', () => {
      const camera = createMockCamera()
      render(<CameraForm initialData={camera} onSubmit={mockOnSubmit} />)

      expect(screen.getByDisplayValue('Test Camera')).toBeInTheDocument()
      expect(screen.getByDisplayValue('rtsp://192.168.1.100:554/stream')).toBeInTheDocument()
      expect(screen.getByDisplayValue('admin')).toBeInTheDocument()
    })

    it('shows Update Camera button in edit mode', () => {
      const camera = createMockCamera()
      render(<CameraForm initialData={camera} onSubmit={mockOnSubmit} />)

      expect(screen.getByRole('button', { name: /update camera/i })).toBeInTheDocument()
    })

    it('shows test connection section in edit mode', () => {
      const camera = createMockCamera()
      render(<CameraForm initialData={camera} onSubmit={mockOnSubmit} />)

      expect(screen.getByText(/test connection/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /^test$/i })).toBeInTheDocument()
    })
  })

  describe('conditional fields', () => {
    it('shows RTSP fields when RTSP type is selected', async () => {
      render(<CameraForm onSubmit={mockOnSubmit} />)

      // RTSP is default
      expect(screen.getByLabelText(/rtsp url/i)).toBeInTheDocument()
      expect(screen.queryByLabelText(/device index/i)).not.toBeInTheDocument()
    })

    // Note: Testing Radix UI Select interaction in jsdom is challenging due to portal/pointer capture issues.
    // The conditional field logic is verified through the 'renders with USB type from initial data' test below.

    it('renders with USB type from initial data', () => {
      const camera = createMockCamera({
        type: 'usb',
        rtsp_url: undefined,
        device_index: 0,
      })
      render(<CameraForm initialData={camera} onSubmit={mockOnSubmit} />)

      expect(screen.getByLabelText(/device index/i)).toBeInTheDocument()
      expect(screen.queryByLabelText(/rtsp url/i)).not.toBeInTheDocument()
    })
  })

  describe('form submission', () => {
    it('calls onSubmit with form data on valid submission', async () => {
      const user = userEvent.setup()
      mockOnSubmit.mockResolvedValueOnce(undefined)

      render(<CameraForm onSubmit={mockOnSubmit} />)

      // Fill required fields
      await user.type(screen.getByLabelText(/camera name/i), 'New Camera')
      await user.type(screen.getByLabelText(/rtsp url/i), 'rtsp://192.168.1.50:554/stream1')

      // Submit the form
      await user.click(screen.getByRole('button', { name: /save camera/i }))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled()
      })

      const submittedData = mockOnSubmit.mock.calls[0][0]
      expect(submittedData.name).toBe('New Camera')
      expect(submittedData.rtsp_url).toBe('rtsp://192.168.1.50:554/stream1')
      expect(submittedData.type).toBe('rtsp')
    })

    it('calls onCancel when cancel button clicked', async () => {
      const user = userEvent.setup()
      render(<CameraForm onSubmit={mockOnSubmit} onCancel={mockOnCancel} />)

      await user.click(screen.getByRole('button', { name: /cancel/i }))

      expect(mockOnCancel).toHaveBeenCalled()
    })

    it('disables buttons when isSubmitting is true', () => {
      render(
        <CameraForm
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
          isSubmitting={true}
        />
      )

      expect(screen.getByRole('button', { name: /save camera/i })).toBeDisabled()
      expect(screen.getByRole('button', { name: /cancel/i })).toBeDisabled()
    })

    it('shows loading indicator when isSubmitting is true', () => {
      render(
        <CameraForm
          onSubmit={mockOnSubmit}
          isSubmitting={true}
        />
      )

      // The button should contain a loader (spinning icon)
      const submitButton = screen.getByRole('button', { name: /save camera/i })
      expect(submitButton.querySelector('svg')).toBeInTheDocument()
    })
  })

  describe('validation', () => {
    it('shows validation error for empty camera name', async () => {
      const user = userEvent.setup()
      render(<CameraForm onSubmit={mockOnSubmit} />)

      // Fill RTSP URL but leave name empty
      await user.type(screen.getByLabelText(/rtsp url/i), 'rtsp://192.168.1.50:554/stream')

      // Try to submit
      await user.click(screen.getByRole('button', { name: /save camera/i }))

      // Validation message should appear
      await waitFor(() => {
        expect(screen.getByText(/camera name is required/i)).toBeInTheDocument()
      })
      expect(mockOnSubmit).not.toHaveBeenCalled()
    })

    it('shows validation error for invalid RTSP URL', async () => {
      const user = userEvent.setup()
      render(<CameraForm onSubmit={mockOnSubmit} />)

      await user.type(screen.getByLabelText(/camera name/i), 'Test Camera')
      await user.type(screen.getByLabelText(/rtsp url/i), 'http://invalid.url')

      await user.click(screen.getByRole('button', { name: /save camera/i }))

      await waitFor(() => {
        expect(screen.getByText(/rtsp url must start with rtsp:\/\/ or rtsps:\/\//i)).toBeInTheDocument()
      })
      expect(mockOnSubmit).not.toHaveBeenCalled()
    })
  })

  describe('test connection', () => {
    it('tests connection successfully', async () => {
      const user = userEvent.setup()
      const testResult: ICameraTestResponse = {
        success: true,
        message: 'Connection successful',
      }
      mockApiClient.cameras.testConnection.mockResolvedValueOnce(testResult)

      const camera = createMockCamera()
      render(<CameraForm initialData={camera} onSubmit={mockOnSubmit} />)

      await user.click(screen.getByRole('button', { name: /^test$/i }))

      await waitFor(() => {
        expect(screen.getByText('Connection successful')).toBeInTheDocument()
      })
      expect(mockApiClient.cameras.testConnection).toHaveBeenCalledWith('cam-123')
    })

    it('shows error message on connection failure', async () => {
      const user = userEvent.setup()
      const testResult: ICameraTestResponse = {
        success: false,
        message: 'Connection refused',
      }
      mockApiClient.cameras.testConnection.mockResolvedValueOnce(testResult)

      const camera = createMockCamera()
      render(<CameraForm initialData={camera} onSubmit={mockOnSubmit} />)

      await user.click(screen.getByRole('button', { name: /^test$/i }))

      await waitFor(() => {
        expect(screen.getByText('Connection refused')).toBeInTheDocument()
      })
    })

    it('shows API error message on request failure', async () => {
      const user = userEvent.setup()
      mockApiClient.cameras.testConnection.mockRejectedValueOnce(
        new ApiError('Network timeout')
      )

      const camera = createMockCamera()
      render(<CameraForm initialData={camera} onSubmit={mockOnSubmit} />)

      await user.click(screen.getByRole('button', { name: /^test$/i }))

      await waitFor(() => {
        expect(screen.getByText('Network timeout')).toBeInTheDocument()
      })
    })

    it('shows generic error message on unknown error', async () => {
      const user = userEvent.setup()
      mockApiClient.cameras.testConnection.mockRejectedValueOnce(new Error('Unknown'))

      const camera = createMockCamera()
      render(<CameraForm initialData={camera} onSubmit={mockOnSubmit} />)

      await user.click(screen.getByRole('button', { name: /^test$/i }))

      await waitFor(() => {
        expect(screen.getByText('Connection test failed')).toBeInTheDocument()
      })
    })

    it('shows loading state during test', async () => {
      const user = userEvent.setup()
      let resolveTest: (value: ICameraTestResponse) => void
      mockApiClient.cameras.testConnection.mockImplementationOnce(
        () => new Promise((resolve) => { resolveTest = resolve })
      )

      const camera = createMockCamera()
      render(<CameraForm initialData={camera} onSubmit={mockOnSubmit} />)

      await user.click(screen.getByRole('button', { name: /^test$/i }))

      // Button should be disabled and show loading
      expect(screen.getByRole('button', { name: /^test$/i })).toBeDisabled()

      // Resolve the promise
      resolveTest!({ success: true, message: 'Success' })

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /^test$/i })).not.toBeDisabled()
      })
    })

    it('displays preview thumbnail on successful test with thumbnail', async () => {
      const user = userEvent.setup()
      const testResult: ICameraTestResponse = {
        success: true,
        message: 'Connection successful',
        thumbnail: 'data:image/jpeg;base64,/9j/4AAQ...',
      }
      mockApiClient.cameras.testConnection.mockResolvedValueOnce(testResult)

      const camera = createMockCamera()
      render(<CameraForm initialData={camera} onSubmit={mockOnSubmit} />)

      await user.click(screen.getByRole('button', { name: /^test$/i }))

      await waitFor(() => {
        expect(screen.getByAltText('Camera preview')).toBeInTheDocument()
      })
    })

    it('shows test button disabled until RTSP URL entered in create mode', () => {
      // In create mode for RTSP cameras, test button is visible but disabled
      // until an RTSP URL is entered
      render(<CameraForm onSubmit={mockOnSubmit} />)

      const testButton = screen.getByRole('button', { name: /^test$/i })
      expect(testButton).toBeDisabled()
    })
  })

  describe('detection zones', () => {
    it('renders zone management components', () => {
      render(<CameraForm onSubmit={mockOnSubmit} />)

      expect(screen.getByTestId('detection-zone-list')).toBeInTheDocument()
      expect(screen.getByTestId('zone-preset-templates')).toBeInTheDocument()
      expect(screen.getByText(/draw custom polygon/i)).toBeInTheDocument()
    })

    it('shows zone drawer when Draw Custom Polygon is clicked', async () => {
      const user = userEvent.setup()
      render(<CameraForm onSubmit={mockOnSubmit} />)

      await user.click(screen.getByText(/draw custom polygon/i))

      expect(screen.getByTestId('detection-zone-drawer')).toBeInTheDocument()
    })

    it('adds zone when zone drawing is completed', async () => {
      const user = userEvent.setup()
      render(<CameraForm onSubmit={mockOnSubmit} />)

      // Start drawing
      await user.click(screen.getByText(/draw custom polygon/i))

      // Complete zone
      await user.click(screen.getByText('Complete Zone'))

      // Zone should be added
      await waitFor(() => {
        expect(screen.getByText('Zone 1')).toBeInTheDocument()
      })
    })

    it('cancels zone drawing', async () => {
      const user = userEvent.setup()
      render(<CameraForm onSubmit={mockOnSubmit} />)

      await user.click(screen.getByText(/draw custom polygon/i))
      expect(screen.getByTestId('detection-zone-drawer')).toBeInTheDocument()

      await user.click(screen.getByText('Cancel Drawing'))

      expect(screen.queryByTestId('detection-zone-drawer')).not.toBeInTheDocument()
    })

    it('adds zone from preset template', async () => {
      const user = userEvent.setup()
      render(<CameraForm onSubmit={mockOnSubmit} />)

      await user.click(screen.getByText('Full Frame Template'))

      await waitFor(() => {
        expect(screen.getByText('Zone 1')).toBeInTheDocument()
      })
    })

    it('deletes a zone', async () => {
      const user = userEvent.setup()
      const camera = createMockCamera({
        detection_zones: [
          { id: 'zone-1', name: 'Zone 1', vertices: [{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 1, y: 1 }], enabled: true },
        ],
      })
      render(<CameraForm initialData={camera} onSubmit={mockOnSubmit} />)

      expect(screen.getByText('Zone 1')).toBeInTheDocument()

      await user.click(screen.getByText('Delete Zone 1'))

      await waitFor(() => {
        expect(screen.queryByText('Zone 1')).not.toBeInTheDocument()
      })
    })

    it('updates a zone', async () => {
      const user = userEvent.setup()
      const camera = createMockCamera({
        detection_zones: [
          { id: 'zone-1', name: 'Zone 1', vertices: [{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 1, y: 1 }], enabled: true },
        ],
      })
      render(<CameraForm initialData={camera} onSubmit={mockOnSubmit} />)

      await user.click(screen.getByText('Update Zone 1'))

      // The mock updates the zone name to 'Updated Zone'
      await waitFor(() => {
        expect(screen.getByText('Updated Zone')).toBeInTheDocument()
      })
    })

    it('hides draw button when 10 zones exist', () => {
      const zones = Array.from({ length: 10 }, (_, i) => ({
        id: `zone-${i}`,
        name: `Zone ${i + 1}`,
        vertices: [{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 1, y: 1 }],
        enabled: true,
      }))
      const camera = createMockCamera({ detection_zones: zones })

      render(<CameraForm initialData={camera} onSubmit={mockOnSubmit} />)

      expect(screen.queryByText(/draw custom polygon/i)).not.toBeInTheDocument()
      expect(screen.getByText(/maximum of 10 zones reached/i)).toBeInTheDocument()
    })
  })

  describe('child components', () => {
    it('renders MotionSettingsSection', () => {
      render(<CameraForm onSubmit={mockOnSubmit} />)

      expect(screen.getByTestId('motion-settings-section')).toBeInTheDocument()
    })

    it('renders DetectionScheduleEditor', () => {
      render(<CameraForm onSubmit={mockOnSubmit} />)

      expect(screen.getByTestId('detection-schedule-editor')).toBeInTheDocument()
    })

    it('renders AnalysisModeSelector with correct source type', () => {
      render(<CameraForm onSubmit={mockOnSubmit} />)

      const selector = screen.getByTestId('analysis-mode-selector')
      expect(selector).toBeInTheDocument()
      expect(selector).toHaveAttribute('data-source-type', 'rtsp')
    })

    it('passes correct source type from initial data', () => {
      const camera = createMockCamera({ source_type: 'protect' })
      render(<CameraForm initialData={camera} onSubmit={mockOnSubmit} />)

      const selector = screen.getByTestId('analysis-mode-selector')
      expect(selector).toHaveAttribute('data-source-type', 'protect')
    })
  })

  describe('frame rate slider', () => {
    it('renders frame rate slider with default value', () => {
      render(<CameraForm onSubmit={mockOnSubmit} />)

      // Default frame rate is 5 FPS
      expect(screen.getByText(/frame rate: 5 fps/i)).toBeInTheDocument()
    })

    it('displays frame rate from initial data', () => {
      const camera = createMockCamera({ frame_rate: 15 })
      render(<CameraForm initialData={camera} onSubmit={mockOnSubmit} />)

      expect(screen.getByText(/frame rate: 15 fps/i)).toBeInTheDocument()
    })
  })
})
