/**
 * useHomekitStatus hook (Story P4-6.1, P5-1.8)
 *
 * TanStack Query hook for fetching and managing HomeKit integration status.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';

export interface HomekitStatus {
  enabled: boolean;
  running: boolean;
  paired: boolean;
  accessory_count: number;
  bridge_name: string;
  setup_code: string | null;
  qr_code_data: string | null;
  port: number;
  error: string | null;
  available: boolean;
}

export interface HomekitResetResponse {
  success: boolean;
  message: string;
  new_setup_code: string | null;
}

export interface HomekitEnableRequest {
  enabled: boolean;
}

/**
 * Pairing information (Story P5-1.8)
 */
export interface HomekitPairing {
  pairing_id: string;
  is_admin: boolean;
  permissions: number;
}

export interface HomekitPairingsResponse {
  pairings: HomekitPairing[];
  count: number;
}

export interface HomekitRemovePairingResponse {
  success: boolean;
  message: string;
  pairing_id: string;
}

const HOMEKIT_QUERY_KEY = ['homekit', 'status'];
const HOMEKIT_PAIRINGS_KEY = ['homekit', 'pairings'];

/**
 * Fetch HomeKit status from the API
 */
async function fetchHomekitStatus(): Promise<HomekitStatus> {
  return apiClient.homekit.getStatus();
}

/**
 * Reset HomeKit pairing
 */
async function resetHomekitPairing(): Promise<HomekitResetResponse> {
  return apiClient.homekit.resetPairing();
}

/**
 * Enable or disable HomeKit
 */
async function updateHomekitEnabled(enabled: boolean): Promise<HomekitStatus> {
  return apiClient.homekit.setEnabled(enabled);
}

/**
 * Hook for fetching HomeKit status with polling support
 *
 * @param options.enabled - Whether to enable the query (default: true)
 * @param options.refetchInterval - Polling interval in ms (default: 10000 for settings page)
 */
export function useHomekitStatus(options?: {
  enabled?: boolean;
  refetchInterval?: number | false;
}) {
  return useQuery({
    queryKey: HOMEKIT_QUERY_KEY,
    queryFn: fetchHomekitStatus,
    enabled: options?.enabled ?? true,
    refetchInterval: options?.refetchInterval ?? false,
    staleTime: 5000, // Consider data stale after 5 seconds
    retry: 1,
  });
}

/**
 * Hook for resetting HomeKit pairing
 */
export function useHomekitReset() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: resetHomekitPairing,
    onSuccess: () => {
      // Invalidate status to refetch with new pairing code
      queryClient.invalidateQueries({ queryKey: HOMEKIT_QUERY_KEY });
    },
  });
}

/**
 * Hook for enabling/disabling HomeKit
 */
export function useHomekitToggle() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: updateHomekitEnabled,
    onSuccess: (data) => {
      // Update cache with new status
      queryClient.setQueryData(HOMEKIT_QUERY_KEY, data);
    },
    onError: () => {
      // Refetch on error to get current state
      queryClient.invalidateQueries({ queryKey: HOMEKIT_QUERY_KEY });
    },
  });
}

// ============================================================================
// Pairings Hooks (Story P5-1.8)
// ============================================================================

/**
 * Fetch HomeKit pairings from the API (Story P5-1.8)
 */
async function fetchHomekitPairings(): Promise<HomekitPairingsResponse> {
  return apiClient.homekit.getPairings();
}

/**
 * Remove a HomeKit pairing (Story P5-1.8)
 */
async function removeHomekitPairing(pairingId: string): Promise<HomekitRemovePairingResponse> {
  return apiClient.homekit.removePairing(pairingId);
}

/**
 * Hook for fetching HomeKit pairings list (Story P5-1.8 AC3)
 *
 * @param options.enabled - Whether to enable the query (default: true)
 */
export function useHomekitPairings(options?: {
  enabled?: boolean;
}) {
  return useQuery({
    queryKey: HOMEKIT_PAIRINGS_KEY,
    queryFn: fetchHomekitPairings,
    enabled: options?.enabled ?? true,
    staleTime: 10000, // Consider data stale after 10 seconds
    retry: 1,
  });
}

/**
 * Hook for removing a HomeKit pairing (Story P5-1.8 AC4)
 */
export function useHomekitRemovePairing() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: removeHomekitPairing,
    onSuccess: () => {
      // Invalidate both pairings and status queries
      queryClient.invalidateQueries({ queryKey: HOMEKIT_PAIRINGS_KEY });
      queryClient.invalidateQueries({ queryKey: HOMEKIT_QUERY_KEY });
    },
  });
}
