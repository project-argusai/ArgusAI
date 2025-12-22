/**
 * useEvents Hook Tests
 *
 * Tests for event data fetching hooks using TanStack Query.
 *
 * Demonstrates:
 * - Testing hooks with QueryClientProvider wrapper
 * - Mocking API client
 * - Testing infinite query pagination
 * - Testing optimistic updates
 * - Testing query invalidation
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEvents, useRecentEvents, useDeleteEvent, useInvalidateEvents } from '@/lib/hooks/useEvents'
import { apiClient } from '@/lib/api-client'
import type { IEventsResponse, IEvent } from '@/types/event'
import React from 'react'

// Mock the API client
vi.mock('@/lib/api-client', () => ({
  apiClient: {
    events: {
      list: vi.fn(),
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
    list: ReturnType<typeof vi.fn>
    delete: ReturnType<typeof vi.fn>
  }
}

// Sample event data - use numeric string ID that can be converted to number
const mockEvent: IEvent = {
  id: '1',
  camera_id: 'cam-1',
  timestamp: '2024-01-15T10:00:00Z',
  description: 'Person detected at front door',
  thumbnail_base64: 'base64data',
  object_count: 1,
  detected_objects: ['person'],
  confidence_score: 85,
  source_type: 'protect',
  is_doorbell_ring: false,
  low_confidence: false,
}

const mockEventsResponse: IEventsResponse = {
  events: [mockEvent],
  total_count: 1,
  offset: 0,
}

describe('useEvents hooks', () => {
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

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          gcTime: 0,
        },
        mutations: {
          retry: false,
        },
      },
    })
    vi.clearAllMocks()
  })

  afterEach(() => {
    queryClient.clear()
  })

  describe('useRecentEvents', () => {
    it('fetches recent events with default limit', async () => {
      mockApiClient.events.list.mockResolvedValueOnce(mockEventsResponse)

      const { result } = renderHook(() => useRecentEvents(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      // Implementation passes all params in a single object
      expect(mockApiClient.events.list).toHaveBeenCalledWith({ skip: 0, limit: 5 })
      expect(result.current.data).toEqual(mockEventsResponse)
    })

    it('fetches recent events with custom limit', async () => {
      mockApiClient.events.list.mockResolvedValueOnce(mockEventsResponse)

      const { result } = renderHook(() => useRecentEvents(10), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(mockApiClient.events.list).toHaveBeenCalledWith({ skip: 0, limit: 10 })
    })

    it('handles API error', async () => {
      const error = new Error('Network error')
      mockApiClient.events.list.mockRejectedValueOnce(error)

      const { result } = renderHook(() => useRecentEvents(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })

      expect(result.current.error).toBe(error)
    })
  })

  describe('useEvents', () => {
    it('fetches events with infinite query', async () => {
      mockApiClient.events.list.mockResolvedValueOnce(mockEventsResponse)

      const { result } = renderHook(() => useEvents(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data?.pages).toHaveLength(1)
      expect(result.current.data?.pages[0]).toEqual(mockEventsResponse)
    })

    it('passes filters to API', async () => {
      mockApiClient.events.list.mockResolvedValueOnce(mockEventsResponse)

      const filters = {
        camera_id: 'cam-1',
        search: 'person',
        analysis_mode: 'multi_frame' as const,
      }

      const { result } = renderHook(() => useEvents(filters), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      // Filters and pagination are combined into a single object
      expect(mockApiClient.events.list).toHaveBeenCalledWith({
        ...filters,
        skip: 0,
        limit: 20,
      })
    })

    it('fetches next page when more data available', async () => {
      // First page: offset 0, 20 events returned, 40 total
      const firstPageEvents = Array.from({ length: 20 }, (_, i) => ({
        ...mockEvent,
        id: `${i + 1}`,
      }))
      const firstPage: IEventsResponse = {
        events: firstPageEvents,
        total_count: 40,
        offset: 0,
      }

      // Second page: offset 20, 20 more events
      const secondPageEvents = Array.from({ length: 20 }, (_, i) => ({
        ...mockEvent,
        id: `${i + 21}`,
      }))
      const secondPage: IEventsResponse = {
        events: secondPageEvents,
        total_count: 40,
        offset: 20,
      }

      mockApiClient.events.list
        .mockResolvedValueOnce(firstPage)
        .mockResolvedValueOnce(secondPage)

      const { result } = renderHook(() => useEvents(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      // nextOffset = 0 + 20 = 20, which is less than 40, so hasNextPage should be true
      expect(result.current.hasNextPage).toBe(true)

      await act(async () => {
        await result.current.fetchNextPage()
      })

      await waitFor(() => {
        expect(result.current.data?.pages).toHaveLength(2)
      })

      expect(mockApiClient.events.list).toHaveBeenCalledTimes(2)
      // The pageParam for second page should be 20 (offset 0 + 20 events)
      expect(mockApiClient.events.list).toHaveBeenLastCalledWith({ skip: 20, limit: 20 })
    })

    it('indicates no more pages when all data loaded', async () => {
      mockApiClient.events.list.mockResolvedValueOnce(mockEventsResponse)

      const { result } = renderHook(() => useEvents(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      // total_count is 1, offset + events.length >= total_count
      expect(result.current.hasNextPage).toBe(false)
    })

    it('includes filters in query key for proper caching', async () => {
      mockApiClient.events.list.mockResolvedValue(mockEventsResponse)

      const { result: result1 } = renderHook(() =>
        useEvents({ camera_id: 'cam-1' }), {
        wrapper: createWrapper(),
      })

      const { result: result2 } = renderHook(() =>
        useEvents({ camera_id: 'cam-2' }), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true)
        expect(result2.current.isSuccess).toBe(true)
      })

      // Should have made two separate API calls for different filters
      expect(mockApiClient.events.list).toHaveBeenCalledTimes(2)
    })
  })

  describe('useDeleteEvent', () => {
    it('deletes event successfully', async () => {
      mockApiClient.events.delete.mockResolvedValueOnce(undefined)
      mockApiClient.events.list.mockResolvedValue(mockEventsResponse)

      const { result } = renderHook(() => useDeleteEvent(), {
        wrapper: createWrapper(),
      })

      await act(async () => {
        await result.current.mutateAsync('1')
      })

      // ID is passed as string to the API client
      expect(mockApiClient.events.delete).toHaveBeenCalledWith('1')
    })

    it('shows success toast on delete', async () => {
      const { toast } = await import('sonner')
      mockApiClient.events.delete.mockResolvedValueOnce(undefined)

      const { result } = renderHook(() => useDeleteEvent(), {
        wrapper: createWrapper(),
      })

      await act(async () => {
        await result.current.mutateAsync('1')
      })

      expect(toast.success).toHaveBeenCalledWith('Event deleted successfully')
    })

    it('shows error toast on delete failure', async () => {
      const { toast } = await import('sonner')
      mockApiClient.events.delete.mockRejectedValueOnce(new Error('Delete failed'))

      const { result } = renderHook(() => useDeleteEvent(), {
        wrapper: createWrapper(),
      })

      try {
        await act(async () => {
          await result.current.mutateAsync('1')
        })
      } catch {
        // Expected to throw
      }

      expect(toast.error).toHaveBeenCalledWith('Failed to delete event')
    })

    it('performs optimistic update', async () => {
      // Set up initial data
      const multiEventResponse: IEventsResponse = {
        events: [
          mockEvent,
          { ...mockEvent, id: '2' },
        ],
        total_count: 2,
        offset: 0,
      }

      mockApiClient.events.list.mockResolvedValue(multiEventResponse)

      // First, populate the cache with events
      const { result: eventsResult } = renderHook(() => useEvents(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(eventsResult.current.isSuccess).toBe(true)
      })

      // Now test delete
      mockApiClient.events.delete.mockImplementation(() =>
        new Promise((resolve) => setTimeout(resolve, 1000))
      )

      const { result: deleteResult } = renderHook(() => useDeleteEvent(), {
        wrapper: createWrapper(),
      })

      // Start deletion but don't await
      act(() => {
        deleteResult.current.mutate('1')
      })

      // Check that the event was optimistically removed
      await waitFor(() => {
        const cachedData = queryClient.getQueryData(['events', {}]) as {
          pages: IEventsResponse[]
        } | undefined

        // The optimistic update should have filtered out event with id '1'
        expect(
          cachedData?.pages[0].events.find((e: IEvent) => e.id === '1')
        ).toBeUndefined()
      })
    })
  })

  describe('useInvalidateEvents', () => {
    it('returns a function that invalidates events queries', async () => {
      mockApiClient.events.list.mockResolvedValue(mockEventsResponse)

      // Set up events in cache
      const { result: eventsResult } = renderHook(() => useEvents(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(eventsResult.current.isSuccess).toBe(true)
      })

      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

      // Get the invalidate function
      const { result: invalidateResult } = renderHook(() => useInvalidateEvents(), {
        wrapper: createWrapper(),
      })

      // Call it
      act(() => {
        invalidateResult.current()
      })

      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['events'] })
    })
  })
})
