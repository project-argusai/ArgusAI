/**
 * Custom hooks for entity management using TanStack Query (Story P4-3.6)
 */

'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient, ApiError } from '@/lib/api-client';
import type { EntityType } from '@/types/entity';

/**
 * Query parameters for fetching entities
 */
export interface UseEntitiesParams {
  limit?: number;
  offset?: number;
  entity_type?: EntityType;
  named_only?: boolean;
  search?: string;
}

/**
 * Hook to fetch paginated entity list
 * @param params Query parameters (limit, offset, entity_type, named_only)
 * @returns Query result with entities data and state
 */
export function useEntities(params: UseEntitiesParams = {}) {
  return useQuery({
    queryKey: ['entities', params],
    queryFn: () => apiClient.entities.list(params),
    staleTime: 30000, // 30 seconds
  });
}

/**
 * Hook to fetch a single entity by ID
 * @param entityId UUID of the entity
 * @param eventLimit Maximum number of recent events to include
 * @returns Query result with entity detail
 */
export function useEntity(entityId: string | null, _eventLimit?: number) {
  return useQuery({
    queryKey: ['entities', entityId],
    queryFn: () => entityId ? apiClient.entities.get(entityId) : null,
    enabled: !!entityId,
    staleTime: 30000,
  });
}

/**
 * Hook to update an entity's name
 * @returns Mutation for updating entity
 */
export function useUpdateEntity() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ entityId, name }: { entityId: string; name: string | null }) =>
      apiClient.entities.update(entityId, { name }),
    onSuccess: (updatedEntity) => {
      // Invalidate entity list
      queryClient.invalidateQueries({ queryKey: ['entities'] });
      // Update the specific entity in cache
      queryClient.setQueryData(['entities', updatedEntity.id], (old: unknown) => {
        if (old && typeof old === 'object') {
          return { ...old, ...updatedEntity };
        }
        return old;
      });
    },
  });
}

/**
 * Hook to delete an entity
 * @returns Mutation for deleting entity
 */
export function useDeleteEntity() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (entityId: string) => apiClient.entities.delete(entityId),
    onSuccess: (_data, entityId) => {
      // Invalidate entity list
      queryClient.invalidateQueries({ queryKey: ['entities'] });
      // Remove the specific entity from cache
      queryClient.removeQueries({ queryKey: ['entities', entityId] });
    },
  });
}

/**
 * Response type for paginated entity events (Story P9-4.2)
 */
export interface EntityEventsResponse {
  entity_id: string;
  events: Array<{
    id: string;
    timestamp: string;
    description: string;
    thumbnail_url: string | null;
    camera_id: string;
    similarity_score: number;
  }>;
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
}

/**
 * Hook to fetch paginated events for an entity (Story P9-4.2)
 * @param entityId UUID of the entity
 * @param page Page number (1-indexed)
 * @param limit Events per page
 * @returns Query result with paginated events
 */
export function useEntityEvents(
  entityId: string | null,
  page: number = 1,
  limit: number = 20
) {
  return useQuery({
    queryKey: ['entities', entityId, 'events', page, limit],
    queryFn: async (): Promise<EntityEventsResponse> => {
      if (!entityId) {
        return {
          entity_id: '',
          events: [],
          total: 0,
          page: 1,
          limit: 20,
          has_more: false,
        };
      }
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/context/entities/${entityId}/events?page=${page}&limit=${limit}`
      );
      if (!response.ok) {
        throw new Error('Failed to fetch entity events');
      }
      return response.json();
    },
    enabled: !!entityId,
    staleTime: 30000,
  });
}

/**
 * Response type for unlink event operation (Story P9-4.3)
 */
export interface UnlinkEventResponse {
  success: boolean;
  message: string;
}

/**
 * Hook to unlink an event from an entity (Story P9-4.3)
 * @returns Mutation for unlinking event
 */
export function useUnlinkEvent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      entityId,
      eventId,
    }: {
      entityId: string;
      eventId: string;
    }): Promise<UnlinkEventResponse> => {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/context/entities/${entityId}/events/${eventId}`,
        {
          method: 'DELETE',
        }
      );
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to unlink event');
      }
      return response.json();
    },
    onSuccess: (_data, { entityId }) => {
      // Invalidate entity events queries to refresh the list
      queryClient.invalidateQueries({ queryKey: ['entities', entityId, 'events'] });
      // Invalidate entity detail to update occurrence count
      queryClient.invalidateQueries({ queryKey: ['entities', entityId] });
      // Invalidate entity list for occurrence count updates
      queryClient.invalidateQueries({ queryKey: ['entities'] });
    },
  });
}

/**
 * Error type guard for API errors
 */
export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}
