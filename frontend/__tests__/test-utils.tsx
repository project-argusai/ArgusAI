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

// Custom render that includes all providers
const customRender = (
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>
) => render(ui, { wrapper: AllProviders, ...options })

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
