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
 * Error type guard for API errors
 */
export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}
