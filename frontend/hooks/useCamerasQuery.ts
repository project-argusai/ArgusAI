/**
 * Custom hooks for camera management using TanStack Query (Story P6-1.4)
 * Replaces useState/useEffect pattern in useCameras.ts with stale-while-revalidate caching
 */

'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient, ApiError } from '@/lib/api-client';
import type { ICameraCreate, ICameraUpdate } from '@/types/camera';

/**
 * Query parameters for fetching cameras
 */
export interface UseCamerasQueryParams {
  /**
   * Optional filter for enabled/disabled cameras
   */
  is_enabled?: boolean;
}

/**
 * Query key factory for cameras
 * Ensures consistent query keys across the app
 */
export const cameraKeys = {
  all: ['cameras'] as const,
  lists: () => [...cameraKeys.all, 'list'] as const,
  list: (filters?: UseCamerasQueryParams) => [...cameraKeys.lists(), filters ?? {}] as const,
  details: () => [...cameraKeys.all, 'detail'] as const,
  detail: (id: string) => [...cameraKeys.details(), id] as const,
};

/**
 * Hook to fetch camera list with TanStack Query caching
 *
 * Features:
 * - Stale time: 30 seconds (data considered fresh for 30s)
 * - Background refetch on window focus
 * - Automatic cache sharing with other components using same query key
 *
 * @param params Optional filters (is_enabled)
 * @returns Query result with cameras data, loading state, error state, and refetch function
 */
export function useCamerasQuery(params: UseCamerasQueryParams = {}) {
  return useQuery({
    queryKey: cameraKeys.list(params),
    queryFn: () => apiClient.cameras.list(params),
    staleTime: 30000, // 30 seconds - data stays fresh for 30s
    refetchOnWindowFocus: true, // Refetch when user returns to tab
    // Note: These are query-level options that override global defaults
  });
}

/**
 * Hook to fetch a single camera by ID
 * @param cameraId UUID of the camera
 * @returns Query result with camera detail
 */
export function useCameraQuery(cameraId: string | null) {
  return useQuery({
    queryKey: cameraKeys.detail(cameraId ?? ''),
    queryFn: () => cameraId ? apiClient.cameras.getById(cameraId) : null,
    enabled: !!cameraId,
    staleTime: 30000,
    refetchOnWindowFocus: true,
  });
}

/**
 * Hook to create a new camera
 * Invalidates cameras list cache on success
 * @returns Mutation for creating camera
 */
export function useCameraCreate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ICameraCreate) => apiClient.cameras.create(data),
    onSuccess: () => {
      // Invalidate all camera list queries to refetch with new camera
      queryClient.invalidateQueries({ queryKey: cameraKeys.lists() });
    },
  });
}

/**
 * Hook to update an existing camera
 * Invalidates cameras list and specific camera cache on success
 * @returns Mutation for updating camera
 */
export function useCameraUpdate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ICameraUpdate }) =>
      apiClient.cameras.update(id, data),
    onSuccess: (updatedCamera) => {
      // Invalidate camera lists
      queryClient.invalidateQueries({ queryKey: cameraKeys.lists() });
      // Update the specific camera in cache
      queryClient.setQueryData(cameraKeys.detail(updatedCamera.id), updatedCamera);
    },
  });
}

/**
 * Hook to delete a camera
 * Removes camera from cache and invalidates list queries
 * @returns Mutation for deleting camera
 */
export function useCameraDelete() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (cameraId: string) => apiClient.cameras.delete(cameraId),
    onSuccess: (_data, cameraId) => {
      // Invalidate camera lists
      queryClient.invalidateQueries({ queryKey: cameraKeys.lists() });
      // Remove the specific camera from cache
      queryClient.removeQueries({ queryKey: cameraKeys.detail(cameraId) });
    },
  });
}

/**
 * Error type guard for API errors
 */
export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}
