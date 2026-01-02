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
 * Entity update data for useUpdateEntity hook (Story P16-3.2)
 */
export interface UpdateEntityData {
  entityId: string;
  name?: string | null;
  entity_type?: 'person' | 'vehicle' | 'unknown';
  is_vip?: boolean;
  is_blocked?: boolean;
  notes?: string | null;
}

/**
 * Hook to update an entity's properties (Story P16-3.2)
 * @returns Mutation for updating entity
 */
export function useUpdateEntity() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ entityId, ...data }: UpdateEntityData) =>
      apiClient.entities.update(entityId, data),
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
        `${process.env.NEXT_PUBLIC_API_URL ?? ''}/api/v1/context/entities/${entityId}/events?page=${page}&limit=${limit}`,
        { credentials: 'include' }
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
        `${process.env.NEXT_PUBLIC_API_URL ?? ''}/api/v1/context/entities/${entityId}/events/${eventId}`,
        {
          method: 'DELETE',
          credentials: 'include',
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
 * Response type for assign event operation (Story P9-4.4)
 */
export interface AssignEventResponse {
  success: boolean;
  message: string;
  action: 'assign' | 'move' | 'none';
  entity_id: string;
  entity_name: string | null;
}

/**
 * Hook to assign an event to an entity (Story P9-4.4)
 * Handles both new assignments and moving events between entities.
 * @returns Mutation for assigning event
 */
export function useAssignEventToEntity() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      eventId,
      entityId,
    }: {
      eventId: string;
      entityId: string;
    }): Promise<AssignEventResponse> => {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? ''}/api/v1/context/events/${eventId}/entity`,
        {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ entity_id: entityId }),
        }
      );
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to assign event');
      }
      return response.json();
    },
    onSuccess: (data) => {
      // Invalidate entity events queries for the target entity
      queryClient.invalidateQueries({ queryKey: ['entities', data.entity_id, 'events'] });
      // Invalidate entity detail to update occurrence count
      queryClient.invalidateQueries({ queryKey: ['entities', data.entity_id] });
      // Invalidate entity list for occurrence count updates
      queryClient.invalidateQueries({ queryKey: ['entities'] });
      // Invalidate events queries to refresh any entity associations displayed on event cards
      queryClient.invalidateQueries({ queryKey: ['events'] });
    },
  });
}

/**
 * Response type for merge entities operation (Story P9-4.5)
 */
export interface MergeEntitiesResponse {
  success: boolean;
  merged_entity_id: string;
  merged_entity_name: string | null;
  events_moved: number;
  deleted_entity_id: string;
  deleted_entity_name: string | null;
  message: string;
}

/**
 * Hook to merge two entities (Story P9-4.5)
 * Moves all events from secondary entity to primary and deletes secondary.
 * @returns Mutation for merging entities
 */
export function useMergeEntities() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      primaryEntityId,
      secondaryEntityId,
    }: {
      primaryEntityId: string;
      secondaryEntityId: string;
    }): Promise<MergeEntitiesResponse> => {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? ''}/api/v1/context/entities/merge`,
        {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            primary_entity_id: primaryEntityId,
            secondary_entity_id: secondaryEntityId,
          }),
        }
      );
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to merge entities');
      }
      return response.json();
    },
    onSuccess: (data) => {
      // Invalidate entity list to refresh after merge
      queryClient.invalidateQueries({ queryKey: ['entities'] });
      // Invalidate the merged entity to get updated occurrence count
      queryClient.invalidateQueries({ queryKey: ['entities', data.merged_entity_id] });
      // Remove the deleted entity from cache
      queryClient.removeQueries({ queryKey: ['entities', data.deleted_entity_id] });
      // Invalidate events queries to refresh any entity associations
      queryClient.invalidateQueries({ queryKey: ['events'] });
    },
  });
}

/**
 * Request type for creating an entity (Story P10-4.2)
 */
export interface CreateEntityRequest {
  entity_type: 'person' | 'vehicle' | 'unknown';
  name?: string | null;
  notes?: string | null;
  is_vip?: boolean;
  is_blocked?: boolean;
  vehicle_color?: string | null;
  vehicle_make?: string | null;
  vehicle_model?: string | null;
  reference_image?: string | null;
}

/**
 * Response type for created entity (Story P10-4.2)
 */
export interface CreatedEntityResponse {
  id: string;
  entity_type: string;
  name: string | null;
  notes: string | null;
  thumbnail_path: string | null;
  first_seen_at: string;
  last_seen_at: string;
  occurrence_count: number;
  is_vip: boolean;
  is_blocked: boolean;
  vehicle_color: string | null;
  vehicle_make: string | null;
  vehicle_model: string | null;
  vehicle_signature: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Hook to create a new entity manually (Story P10-4.2)
 * @returns Mutation for creating entity
 */
export function useCreateEntity() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateEntityRequest): Promise<CreatedEntityResponse> =>
      apiClient.entities.create(data),
    onSuccess: () => {
      // Invalidate entity list to refresh with new entity
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
