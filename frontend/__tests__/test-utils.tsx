import React, { ReactElement } from 'react'
import { render, RenderOptions } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Create a fresh QueryClient for each test
const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  })

interface WrapperProps {
  children: React.ReactNode
}

// All-in-one provider wrapper for tests
function AllProviders({ children }: WrapperProps) {
  const queryClient = createTestQueryClient()

  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  )
}

import userEvent from '@testing-library/user-event'

// Custom render that includes all providers and returns user for interactions
const customRender = (
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>
) => {
  const user = userEvent.setup()
  return {
    user,
    ...render(ui, { wrapper: AllProviders, ...options })
  }
}

// Re-export everything from testing-library
export * from '@testing-library/react'
export { userEvent } from '@testing-library/user-event'

// Override render with our custom render
export { customRender as render }

// Helper to create a QueryClient wrapper for specific tests
export function createQueryClientWrapper() {
  const queryClient = createTestQueryClient()
  return function QueryClientWrapper({ children }: WrapperProps) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    )
  }
}

// =============================================================================
// Mock Data Factories for Type-Safe Testing
// Story P14-4.4: Centralized test fixtures with complete type coverage
// =============================================================================

import type { IEvent } from '@/types/event'
import type { ICamera } from '@/types/camera'
import type { INotification } from '@/types/notification'
import type { IAlertRule } from '@/types/alert-rule'

/**
 * Create a type-safe mock event with all required fields
 * @param overrides - Partial event fields to override defaults
 */
export const mockEvent = (overrides: Partial<IEvent> = {}): IEvent => ({
  id: 'test-event-1',
  camera_id: 'test-camera-1',
  camera_name: 'Front Door',
  timestamp: new Date().toISOString(),
  description: 'A person was detected walking in the driveway',
  confidence: 85,
  objects_detected: ['person'],
  thumbnail_path: '/thumbnails/test.jpg',
  thumbnail_base64: null,
  alert_triggered: false,
  source_type: 'protect',
  smart_detection_type: 'person',
  is_doorbell_ring: false,
  analysis_mode: 'single_frame',
  frame_count_used: 1,
  fallback_reason: null,
  created_at: new Date().toISOString(),
  // Story P3-6.1 & P3-6.2: AI confidence fields
  ai_confidence: 85,
  low_confidence: false,
  vague_reason: null,
  // Story P3-6.4: Re-analysis fields
  reanalyzed_at: null,
  reanalysis_count: 0,
  // Story P2-5.3: AI provider tracking
  provider_used: 'openai',
  // Story P3-7.1: Cost tracking
  ai_cost: null,
  // Story P3-7.5: Key frames
  key_frames_base64: null,
  frame_timestamps: null,
  // Story P4-5.1: User feedback
  feedback: null,
  // Story P4-7.2: Anomaly scoring
  anomaly_score: null,
  // Story P2-4.4: Correlation
  correlation_group_id: null,
  correlated_events: undefined,
  // Story P9-4.4: Entity association
  entity_id: null,
  entity_name: null,
  // Story P8-3.2: Video storage
  video_path: null,
  ...overrides,
})

/**
 * Create a type-safe mock camera with all required fields
 * @param overrides - Partial camera fields to override defaults
 */
export const mockCamera = (overrides: Partial<ICamera> = {}): ICamera => ({
  id: 'test-camera-1',
  name: 'Front Door',
  type: 'rtsp',
  rtsp_url: 'rtsp://192.168.1.100:554/stream1',
  username: 'admin',
  device_index: undefined,
  frame_rate: 5,
  is_enabled: true,
  motion_enabled: true,
  motion_sensitivity: 'medium',
  motion_cooldown: 30,
  motion_algorithm: 'mog2',
  detection_zones: null,
  detection_schedule: null,
  analysis_mode: 'single_frame',
  homekit_stream_quality: 'medium',
  audio_enabled: false,
  audio_codec: null,
  audio_event_types: null,
  audio_threshold: null,
  source_type: 'protect',
  protect_controller_id: null,
  protect_camera_id: null,
  protect_camera_type: null,
  smart_detection_types: null,
  is_doorbell: false,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...overrides,
})

/**
 * Create a type-safe mock notification with all required fields
 * @param overrides - Partial notification fields to override defaults
 */
export const mockNotification = (overrides: Partial<INotification> = {}): INotification => ({
  id: 'test-notification-1',
  event_id: 'test-event-1',
  rule_id: 'test-rule-1',
  rule_name: 'Person Detection',
  event_description: 'A person was detected at the front door',
  thumbnail_url: '/api/v1/thumbnails/test.jpg',
  read: false,
  created_at: new Date().toISOString(),
  is_doorbell_ring: false,
  ...overrides,
})

/**
 * Create a type-safe mock alert rule with all required fields
 * @param overrides - Partial alert rule fields to override defaults
 */
export const mockAlertRule = (overrides: Partial<IAlertRule> = {}): IAlertRule => ({
  id: 'test-rule-1',
  name: 'Person Detection Alert',
  is_enabled: true,
  conditions: {
    object_types: ['person'],
    cameras: [],
    min_confidence: 70,
  },
  actions: {
    dashboard_notification: true,
  },
  cooldown_minutes: 5,
  last_triggered_at: null,
  trigger_count: 0,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  entity_id: null,
  entity_match_mode: 'any',
  entity_name: null,
  ...overrides,
})

/**
 * Create multiple mock events for list testing
 * @param count - Number of events to create
 * @param baseOverrides - Common overrides for all events
 */
export const mockEventList = (count: number, baseOverrides: Partial<IEvent> = {}): IEvent[] =>
  Array.from({ length: count }, (_, i) =>
    mockEvent({
      id: `test-event-${i + 1}`,
      timestamp: new Date(Date.now() - i * 60000).toISOString(),
      ...baseOverrides,
    })
  )

/**
 * Create multiple mock cameras for list testing
 * @param count - Number of cameras to create
 * @param baseOverrides - Common overrides for all cameras
 */
export const mockCameraList = (count: number, baseOverrides: Partial<ICamera> = {}): ICamera[] =>
  Array.from({ length: count }, (_, i) =>
    mockCamera({
      id: `test-camera-${i + 1}`,
      name: `Camera ${i + 1}`,
      ...baseOverrides,
    })
  )

/**
 * Create multiple mock notifications for list testing
 * @param count - Number of notifications to create
 * @param baseOverrides - Common overrides for all notifications
 */
export const mockNotificationList = (count: number, baseOverrides: Partial<INotification> = {}): INotification[] =>
  Array.from({ length: count }, (_, i) =>
    mockNotification({
      id: `test-notification-${i + 1}`,
      event_id: `test-event-${i + 1}`,
      created_at: new Date(Date.now() - i * 60000).toISOString(),
      ...baseOverrides,
    })
  )
