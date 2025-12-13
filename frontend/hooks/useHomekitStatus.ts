/**
 * useHomekitStatus hook (Story P4-6.1)
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

const HOMEKIT_QUERY_KEY = ['homekit', 'status'];

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
