/**
 * useHomekitStatus hook (Story P4-6.1, P5-1.8, P7-1.1, P7-1.2, P7-1.3, P7-1.4, P7-3.3)
 *
 * TanStack Query hook for fetching and managing HomeKit integration status.
 * Story P7-1.1 adds useHomekitDiagnostics hook for diagnostic data.
 * Story P7-1.2 adds useHomekitTestConnectivity hook for connectivity testing.
 * Story P7-1.3 adds useHomekitTestEvent hook for triggering test events.
 * Story P7-1.4 adds sensor_deliveries and camera_name to diagnostics.
 * Story P7-3.3 adds useHomekitTestStream hook for camera stream testing.
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
// Diagnostics Types (Story P7-1.1, P7-1.4)
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
 * Last event delivery info (Story P7-1.1, P7-1.4)
 */
export interface HomekitLastEventDelivery {
  camera_id: string;
  camera_name?: string | null;  // Story P7-1.4 (optional for backward compat)
  sensor_type: string;
  timestamp: string;
  delivered: boolean;
}

/**
 * Diagnostics response (Story P7-1.1, P7-1.4)
 */
export interface HomekitDiagnosticsResponse {
  bridge_running: boolean;
  mdns_advertising: boolean;
  network_binding: HomekitNetworkBinding | null;
  connected_clients: number;
  last_event_delivery: HomekitLastEventDelivery | null;
  sensor_deliveries: HomekitLastEventDelivery[];  // Story P7-1.4 AC3
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
    onSuccess: () => {
      // Refetch status to get complete data including 'available' field
      // (enable/disable endpoints return partial response)
      queryClient.invalidateQueries({ queryKey: HOMEKIT_QUERY_KEY });
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
// Diagnostics Hooks (Story P7-1.1, P7-1.4)
// ============================================================================

/**
 * Fetch HomeKit diagnostics from the API (Story P7-1.1, P7-1.4)
 */
async function fetchHomekitDiagnostics(): Promise<HomekitDiagnosticsResponse> {
  const data = await apiClient.homekit.getDiagnostics();
  // Cast the API response to our typed interface (API returns generic strings, we type them)
  return {
    ...data,
    sensor_deliveries: data.sensor_deliveries || [],  // Story P7-1.4 AC3
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
 * Connectivity test response (Story P7-1.2)
 */
export interface HomekitConnectivityTestResponse {
  mdns_visible: boolean;
  discovered_as: string | null;
  port_accessible: boolean;
  network_binding: HomekitNetworkBinding | null;
  firewall_issues: string[];
  recommendations: string[];
  test_duration_ms: number;
}

/**
 * Test HomeKit connectivity via the API (Story P7-1.2)
 */
async function testHomekitConnectivity(): Promise<HomekitConnectivityTestResponse> {
  return apiClient.homekit.testConnectivity();
}

/**
 * Hook for testing HomeKit connectivity (Story P7-1.2 AC6)
 *
 * This is a mutation hook since connectivity test is an action that takes time
 * and should only run when explicitly triggered (not on component mount).
 */
export function useHomekitTestConnectivity() {
  return useMutation({
    mutationFn: testHomekitConnectivity,
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

// ============================================================================
// Stream Test Types and Hooks (Story P7-3.3)
// ============================================================================

const HOMEKIT_STREAM_TEST_KEY = ['homekit', 'stream-test'];

/**
 * Stream test response (Story P7-3.3 AC3)
 */
export interface HomekitStreamTestResponse {
  success: boolean;
  rtsp_accessible: boolean;
  ffmpeg_compatible: boolean;
  source_resolution: string | null;
  source_fps: number | null;
  source_codec: string | null;
  target_resolution: string | null;
  target_fps: number | null;
  target_bitrate: number | null;
  estimated_latency_ms: number | null;
  ffmpeg_command: string | null;
  error: string | null;
  test_duration_ms: number;
}

/**
 * Test camera stream via the API (Story P7-3.3)
 */
async function testHomekitStream(cameraId: string): Promise<HomekitStreamTestResponse> {
  return apiClient.homekit.testCameraStream(cameraId);
}

/**
 * Hook for testing HomeKit camera streaming (Story P7-3.3 AC4)
 *
 * Uses a mutation pattern since stream tests are user-initiated
 * and take time to complete.
 */
export function useHomekitTestStream() {
  return useMutation({
    mutationFn: testHomekitStream,
    mutationKey: HOMEKIT_STREAM_TEST_KEY,
  });
}
