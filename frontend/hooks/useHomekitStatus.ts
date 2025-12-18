/**
 * useHomekitStatus hook (Story P4-6.1, P5-1.8, P7-1.1)
 *
 * TanStack Query hook for fetching and managing HomeKit integration status.
 * Story P7-1.1 adds useHomekitDiagnostics hook for diagnostic data.
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
const HOMEKIT_DIAGNOSTICS_KEY = ['homekit', 'diagnostics'];
const HOMEKIT_CONNECTIVITY_KEY = ['homekit', 'connectivity'];

// ============================================================================
// Diagnostics Types (Story P7-1.1)
// ============================================================================

/**
 * Diagnostic log entry (Story P7-1.1, P7-1.3)
 */
export interface HomekitDiagnosticEntry {
  timestamp: string;
  level: 'debug' | 'info' | 'warning' | 'error';
  category: 'lifecycle' | 'pairing' | 'event' | 'delivery' | 'network' | 'mdns';
  message: string;
  details?: Record<string, unknown>;
}

/**
 * Network binding info (Story P7-1.1)
 */
export interface HomekitNetworkBinding {
  ip: string;
  port: number;
  interface?: string | null;
}

/**
 * Last event delivery info (Story P7-1.1)
 */
export interface HomekitLastEventDelivery {
  camera_id: string;
  sensor_type: string;
  timestamp: string;
  delivered: boolean;
}

/**
 * Diagnostics response (Story P7-1.1)
 */
export interface HomekitDiagnosticsResponse {
  bridge_running: boolean;
  mdns_advertising: boolean;
  network_binding: HomekitNetworkBinding | null;
  connected_clients: number;
  last_event_delivery: HomekitLastEventDelivery | null;
  recent_logs: HomekitDiagnosticEntry[];
  warnings: string[];
  errors: string[];
}

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

// ============================================================================
// Diagnostics Hooks (Story P7-1.1)
// ============================================================================

/**
 * Fetch HomeKit diagnostics from the API (Story P7-1.1)
 */
async function fetchHomekitDiagnostics(): Promise<HomekitDiagnosticsResponse> {
  const data = await apiClient.homekit.getDiagnostics();
  // Cast the API response to our typed interface (API returns generic strings, we type them)
  return {
    ...data,
    recent_logs: data.recent_logs.map((log) => ({
      ...log,
      level: log.level as HomekitDiagnosticEntry['level'],
      category: log.category as HomekitDiagnosticEntry['category'],
    })),
  };
}

/**
 * Hook for fetching HomeKit diagnostics with polling support (Story P7-1.1 AC5, AC6)
 *
 * @param options.enabled - Whether to enable the query (default: true)
 * @param options.refetchInterval - Polling interval in ms (default: 5000 for diagnostics panel)
 */
export function useHomekitDiagnostics(options?: {
  enabled?: boolean;
  refetchInterval?: number | false;
}) {
  return useQuery({
    queryKey: HOMEKIT_DIAGNOSTICS_KEY,
    queryFn: fetchHomekitDiagnostics,
    enabled: options?.enabled ?? true,
    refetchInterval: options?.refetchInterval ?? 5000, // 5-second polling for diagnostics
    staleTime: 2000, // Consider data stale after 2 seconds
    retry: 1,
  });
}

// ============================================================================
// Connectivity Test Types and Hooks (Story P7-1.2)
// ============================================================================

/**
 * Connectivity test result (Story P7-1.2)
 */
export interface HomekitConnectivityResult {
  mdns_visible: boolean;
  discovered_as: string | null;
  port_accessible: boolean;
  firewall_issues: string[];
  bind_address: string;
  port: number;
  bridge_name: string;
  test_timestamp: string;
  troubleshooting_hints: string[];
}

/**
 * Test HomeKit bridge connectivity (Story P7-1.2)
 */
async function testHomekitConnectivity(): Promise<HomekitConnectivityResult> {
  return apiClient.homekit.testConnectivity();
}

/**
 * Hook for testing HomeKit connectivity (Story P7-1.2 AC6)
 *
 * Uses a mutation pattern since connectivity tests are user-initiated
 * and can take several seconds to complete.
 */
export function useHomekitConnectivity() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: testHomekitConnectivity,
    mutationKey: HOMEKIT_CONNECTIVITY_KEY,
    onSuccess: () => {
      // Optionally refresh diagnostics after a connectivity test
      queryClient.invalidateQueries({ queryKey: HOMEKIT_DIAGNOSTICS_KEY });
    },
  });
}

// ============================================================================
// Test Event Types and Hooks (Story P7-1.3)
// ============================================================================

const HOMEKIT_TEST_EVENT_KEY = ['homekit', 'test-event'];

/**
 * Event types that can be triggered (Story P7-1.3)
 */
export type HomekitTestEventType = 'motion' | 'occupancy' | 'vehicle' | 'animal' | 'package' | 'doorbell';

/**
 * Test event request parameters (Story P7-1.3)
 */
export interface HomekitTestEventRequest {
  camera_id: string;
  event_type: HomekitTestEventType;
}

/**
 * Test event result (Story P7-1.3)
 */
export interface HomekitTestEventResult {
  success: boolean;
  message: string;
  camera_id: string;
  event_type: string;
  sensor_name: string | null;
  delivered_to_clients: number;
  timestamp: string;
}

/**
 * Trigger a test HomeKit event (Story P7-1.3)
 */
async function triggerHomekitTestEvent(request: HomekitTestEventRequest): Promise<HomekitTestEventResult> {
  return apiClient.homekit.testEvent(request);
}

/**
 * Hook for triggering a test HomeKit event (Story P7-1.3 AC5)
 *
 * Uses a mutation pattern since test events are user-initiated
 * and modify sensor state.
 */
export function useHomekitTestEvent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: triggerHomekitTestEvent,
    mutationKey: HOMEKIT_TEST_EVENT_KEY,
    onSuccess: () => {
      // Refresh diagnostics after a test event to show delivery confirmation
      queryClient.invalidateQueries({ queryKey: HOMEKIT_DIAGNOSTICS_KEY });
    },
  });
}
