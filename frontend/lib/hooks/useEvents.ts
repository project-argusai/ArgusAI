/**
 * Custom hooks for event data fetching using TanStack Query
 */

import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import type { IEventFilters, IEvent, IEventsResponse } from '@/types/event';
import { toast } from 'sonner';

const EVENTS_PER_PAGE = 20;

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
