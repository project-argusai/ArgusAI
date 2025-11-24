/**
 * Custom hooks for event data fetching using TanStack Query
 */

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import type { IEventFilters, IEvent, IEventsResponse } from '@/types/event';
import { toast } from 'sonner';

const EVENTS_PER_PAGE = 20;

/**
 * Simple query for recent events (dashboard use)
 * Auto-refetches every 10 seconds to pick up new events
 */
export function useRecentEvents(limit: number = 5) {
  return useQuery({
    queryKey: ['events', 'recent', limit],
    queryFn: () => apiClient.events.list({}, { skip: 0, limit }),
    staleTime: 10 * 1000, // 10 seconds
    refetchInterval: 10 * 1000, // Poll every 10 seconds for new events
  });
}

/**
 * Hook to invalidate all event queries (call when new events arrive via WebSocket)
 */
export function useInvalidateEvents() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ['events'] });
}

/**
 * Infinite query for events timeline with filters
 */
export function useEvents(filters: IEventFilters = {}) {
  return useInfiniteQuery({
    queryKey: ['events', filters],
    queryFn: async ({ pageParam = 0 }) => {
      return apiClient.events.list(filters, {
        skip: pageParam,
        limit: EVENTS_PER_PAGE,
      });
    },
    getNextPageParam: (lastPage) => {
      const nextOffset = lastPage.offset + lastPage.events.length;
      return nextOffset < lastPage.total_count ? nextOffset : undefined;
    },
    initialPageParam: 0,
    staleTime: 30 * 1000, // 30 seconds
  });
}

/**
 * Mutation for deleting an event with optimistic UI update
 */
export function useDeleteEvent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (eventId: string) => apiClient.events.delete(eventId),
    onMutate: async (eventId) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['events'] });

      // Snapshot previous value
      const previousEvents = queryClient.getQueriesData({ queryKey: ['events'] });

      // Optimistically remove the event from all queries
      queryClient.setQueriesData(
        { queryKey: ['events'] },
        (old: unknown) => {
          if (!old || typeof old !== 'object' || !('pages' in old)) return old;

          const data = old as { pages: IEventsResponse[] };
          return {
            ...data,
            pages: data.pages.map((page) => ({
              ...page,
              events: page.events.filter((event: IEvent) => event.id !== eventId),
              total_count: page.total_count - 1,
            })),
          };
        }
      );

      return { previousEvents };
    },
    onError: (error, eventId, context) => {
      // Rollback on error
      if (context?.previousEvents) {
        context.previousEvents.forEach(([queryKey, data]) => {
          queryClient.setQueryData(queryKey, data);
        });
      }
      toast.error('Failed to delete event');
      console.error('Delete event error:', error);
    },
    onSuccess: () => {
      toast.success('Event deleted successfully');
    },
    onSettled: () => {
      // Refetch after mutation (success or error)
      queryClient.invalidateQueries({ queryKey: ['events'] });
    },
  });
}
