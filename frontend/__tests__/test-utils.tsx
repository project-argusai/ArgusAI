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

// Mock data factories for common test scenarios
export const mockEvent = (overrides = {}) => ({
  id: 'test-event-1',
  camera_id: 'test-camera-1',
  timestamp: new Date().toISOString(),
  description: 'A person was detected walking in the driveway',
  confidence: 85,
  objects_detected: ['person'],
  thumbnail_path: '/thumbnails/test.jpg',
  alert_triggered: false,
  source_type: 'protect' as const,
  smart_detection_type: 'person',
  is_doorbell_ring: false,
  analysis_mode: 'single_frame' as const,
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
  ...overrides,
})

export const mockCamera = (overrides = {}) => ({
  id: 'test-camera-1',
  name: 'Front Door',
  type: 'protect' as const,
  is_enabled: true,
  source_type: 'protect' as const,
  analysis_mode: 'single_frame' as const,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...overrides,
})
