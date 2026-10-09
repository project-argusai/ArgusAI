/**
 * Hooks for vehicle license-plate enrolment.
 * Plate text is never cached: only status and "on file" records are.
 */

'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '@/lib/api-client';

/** Whether plate recognition is switched on (and has its salt). */
export function usePlateStatus(enabled = true) {
  return useQuery({
    queryKey: ['plate-status'],
    queryFn: () => apiClient.entities.plateStatus(),
    staleTime: 60000,
    enabled,
  });
}

/** Saved-plate records (ids only) for a vehicle. */
export function useEntityPlates(entityId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ['entity-plates', entityId],
    queryFn: () => apiClient.entities.listPlates(entityId as string),
    enabled: enabled && !!entityId,
  });
}

/** Save a plate. The variables hold the plate only for the request. */
export function useAddPlate(entityId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (plate: string) => apiClient.entities.addPlate(entityId, plate),
    // Keep the plate out of the mutation cache after it settles.
    gcTime: 0,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['entity-plates', entityId] });
    },
  });
}

export function useRemovePlate(entityId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (plateId: string) => apiClient.entities.removePlate(entityId, plateId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['entity-plates', entityId] });
    },
  });
}
