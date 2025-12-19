/**
 * API Client for ArgusAI Backend
 * Base URL configured via NEXT_PUBLIC_API_URL environment variable
 */

import type {
  ICamera,
  ICameraCreate,
  ICameraUpdate,
  ICameraTestResponse,
} from '@/types/camera';
import type {
  IEvent,
  IEventFilters,
  IEventsResponse,
  IEventFeedback,  // Story P4-5.1
  IFeedbackStats,  // Story P4-5.2
  IPromptInsightsResponse,  // Story P4-5.4
  IApplySuggestionRequest,  // Story P4-5.4
  IApplySuggestionResponse,  // Story P4-5.4
  IABTestResultsResponse,  // Story P4-5.4
  IPromptHistoryResponse,  // Story P4-5.4
} from '@/types/event';
import type {
  SystemSettings,
  StorageStats,
  AIKeyTestRequest,
  AIKeyTestResponse,
  DeleteDataResponse,
  IAIUsageResponse,
  IAIUsageQueryParams,
  ICostCapStatus,
  MQTTConfigResponse,
  MQTTConfigUpdate,
  MQTTStatusResponse,
  MQTTTestRequest,
  MQTTTestResponse,
  MQTTPublishDiscoveryResponse,
} from '@/types/settings';
import type {
  IAlertRule,
  IAlertRuleCreate,
  IAlertRuleUpdate,
  IAlertRuleListResponse,
  IAlertRuleTestRequest,
  IAlertRuleTestResponse,
  IWebhookTestRequest,
  IWebhookTestResponse,
  IWebhookLogsFilter,
  IWebhookLogsResponse,
} from '@/types/alert-rule';
import type {
  INotification,
  INotificationListResponse,
  IMarkReadResponse,
  IDeleteNotificationResponse,
  IBulkDeleteResponse,
} from '@/types/notification';
import type {
  SystemHealth,
  LogsResponse,
  LogsQueryParams,
  LogFilesResponse,
} from '@/types/monitoring';
import type {
  IUser,
  ILoginRequest,
  ILoginResponse,
  IChangePasswordRequest,
  IMessageResponse,
  ISetupStatusResponse,
} from '@/types/auth';
import type {
  IBackupResponse,
  IRestoreResponse,
  IBackupListResponse,
  IValidationResponse,
  IBackupOptions,
  IRestoreOptions,
} from '@/types/backup';
import type {
  IDiscoveryResponse,
  IDiscoveryStatusResponse,
  IDeviceDetailsResponse,
  IDiscoveredDevice,
  IDiscoveredCameraDetails,
  IStreamProfile,
  IDeviceInfo,
  ITestConnectionResponse,
} from '@/types/discovery';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_V1_PREFIX = '/api/v1';

// Exported types for Protect cameras
export interface ProtectDiscoveredCamera {
  protect_id: string;
  protect_camera_id: string;
  name: string;
  type: string;
  model: string;
  mac: string;
  host: string | null;
  is_connected: boolean;
  is_online?: boolean;
  is_doorbell: boolean;
  has_package_camera: boolean;
  smart_detect_types: string[];
  is_enabled_for_ai: boolean;
  event_filters: string[];
  camera_id?: number; // Database camera ID if enabled
  analysis_mode?: string;
  is_new?: boolean;
}

// Token storage key
const AUTH_TOKEN_KEY = 'auth_token';

/**
 * Get stored auth token
 */
function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

/**
 * Set auth token in localStorage
 */
export function setAuthToken(token: string): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

/**
 * Clear auth token from localStorage
 */
export function clearAuthToken(): void {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

/**
 * Get headers including auth token for direct fetch calls
 */
function getAuthHeaders(): HeadersInit {
  const headers: HeadersInit = {};
  const token = getAuthToken();
  if (token) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

/**
 * Custom API error class
 */
export class ApiError extends Error {
  statusCode: number;
  details?: unknown;

  constructor(message: string, statusCode: number, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.statusCode = statusCode;
    this.details = details;
  }
}

/**
 * Base fetch wrapper with error handling
 */
async function apiFetch<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE_URL}${API_V1_PREFIX}${endpoint}`;

  try {
    // Build headers with auth token if available
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options?.headers,
    };

    const token = getAuthToken();
    console.log('[API] Request to:', endpoint, 'Token present:', !!token);
    if (token) {
      (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(url, {
      ...options,
      credentials: 'include',  // Also send cookies for JWT auth
      headers,
    });

    // Parse response body
    const data = await response.json().catch(() => null);

    if (!response.ok) {
      const errorMessage = data?.detail || `HTTP ${response.status}: ${response.statusText}`;
      throw new ApiError(errorMessage, response.status, data);
    }

    return data as T;
  } catch (error) {
    // Re-throw ApiError as-is
    if (error instanceof ApiError) {
      throw error;
    }

    // Network or parsing errors
    if (error instanceof Error) {
      throw new ApiError(
        error.message || 'Network error occurred',
        0,
        error
      );
    }

    // Unknown errors
    throw new ApiError('An unexpected error occurred', 0, error);
  }
}

/**
 * Camera API client
 */
export const apiClient = {
  cameras: {
    /**
     * Get all cameras
     */
    list: async (): Promise<ICamera[]> => {
      return apiFetch('/cameras');
    },

    /**
     * Get single camera by ID
     */
    get: async (id: number): Promise<ICamera> => {
      return apiFetch(`/cameras/${id}`);
    },

    /**
     * Create new camera
     */
    create: async (camera: ICameraCreate): Promise<ICamera> => {
      return apiFetch('/cameras', {
        method: 'POST',
        body: JSON.stringify(camera),
      });
    },

    /**
     * Update camera
     */
    update: async (id: number, camera: ICameraUpdate): Promise<ICamera> => {
      return apiFetch(`/cameras/${id}`, {
        method: 'PUT',
        body: JSON.stringify(camera),
      });
    },

    /**
     * Delete camera
     */
    delete: async (id: number): Promise<void> => {
      return apiFetch(`/cameras/${id}`, {
        method: 'DELETE',
      });
    },

    /**
     * Test camera connection
     */
    test: async (id: number): Promise<ICameraTestResponse> => {
      return apiFetch(`/cameras/${id}/test`, {
        method: 'POST',
      });
    },

    /**
     * Test camera connection with provided credentials (before creating)
     */
    testConnection: async (data: {
      rtsp_url?: string;
      usb_device_index?: number;
      username?: string;
      password?: string;
    }): Promise<ICameraTestResponse> => {
      return apiFetch('/cameras/test', {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },

    /**
     * Start camera streaming
     */
    start: async (id: number): Promise<{ status: string; camera_id: number }> => {
      return apiFetch(`/cameras/${id}/start`, {
        method: 'POST',
      });
    },

    /**
     * Stop camera streaming
     */
    stop: async (id: number): Promise<{ status: string; camera_id: number }> => {
      return apiFetch(`/cameras/${id}/stop`, {
        method: 'POST',
      });
    },

    /**
     * Get live preview frame for camera
     */
    getPreviewUrl: (id: number): string => {
      return `${API_BASE_URL}${API_V1_PREFIX}/cameras/${id}/preview`;
    },

    /**
     * Get camera preview with base64 thumbnail
     */
    preview: async (id: number | string): Promise<{ thumbnail_base64?: string; thumbnail_path?: string }> => {
      return apiFetch(`/cameras/${id}/preview`);
    },

    /**
     * Trigger manual analysis of camera frame
     */
    analyze: async (id: number | string): Promise<{ event_id?: number; message: string }> => {
      return apiFetch(`/cameras/${id}/analyze`, {
        method: 'POST',
      });
    },
  },

  events: {
    /**
     * Get events with filtering and pagination
     */
    list: async (filters?: IEventFilters): Promise<IEventsResponse> => {
      const params = new URLSearchParams();
      if (filters) {
        if (filters.skip !== undefined) params.set('skip', String(filters.skip));
        if (filters.limit !== undefined) params.set('limit', String(filters.limit));
        if (filters.camera_id !== undefined) params.set('camera_id', String(filters.camera_id));
        if (filters.start_time) params.set('start_time', filters.start_time);
        if (filters.end_time) params.set('end_time', filters.end_time);
        if (filters.source_type) params.set('source_type', filters.source_type);
        if (filters.smart_detection_type) params.set('smart_detection_type', filters.smart_detection_type);
        if (filters.search) params.set('search', filters.search);
        if (filters.time_range) params.set('time_range', filters.time_range);
        if (filters.has_thumbnail !== undefined) params.set('has_thumbnail', String(filters.has_thumbnail));
      }
      const queryString = params.toString();
      return apiFetch(`/events${queryString ? `?${queryString}` : ''}`);
    },

    /**
     * Get single event by ID
     */
    get: async (id: number): Promise<IEvent> => {
      return apiFetch(`/events/${id}`);
    },

    /**
     * Delete single event
     */
    delete: async (id: number): Promise<void> => {
      return apiFetch(`/events/${id}`, {
        method: 'DELETE',
      });
    },

    /**
     * Delete multiple events
     */
    deleteMany: async (ids: number[]): Promise<{ deleted_count: number }> => {
      return apiFetch('/events/bulk-delete', {
        method: 'DELETE',
        body: JSON.stringify({ event_ids: ids }),
      });
    },

    /**
     * Delete all events
     */
    deleteAll: async (): Promise<{ deleted_count: number }> => {
      return apiFetch('/events/all', {
        method: 'DELETE',
      });
    },

    /**
     * Get event thumbnail URL
     */
    getThumbnailUrl: (id: number): string => {
      return `${API_BASE_URL}${API_V1_PREFIX}/events/${id}/thumbnail`;
    },

    /**
     * Get event statistics
     */
    stats: async (params?: {
      days?: number;
      camera_id?: number;
    }): Promise<{
      total_events: number;
      events_by_day: Array<{ date: string; count: number }>;
      events_by_camera: Array<{ camera_id: number; camera_name: string; count: number }>;
      events_by_hour: Array<{ hour: number; count: number }>;
    }> => {
      const searchParams = new URLSearchParams();
      if (params?.days) searchParams.set('days', String(params.days));
      if (params?.camera_id) searchParams.set('camera_id', String(params.camera_id));
      const queryString = searchParams.toString();
      return apiFetch(`/events/stats${queryString ? `?${queryString}` : ''}`);
    },

    /**
     * Get correlated events for a specific event (Story P3-2.5)
     * @param id Event ID
     * @param params Optional parameters
     * @returns List of correlated events sharing the same correlation_group_id
     */
    getCorrelated: async (id: number, params?: {
      limit?: number;
    }): Promise<{
      event_id: number;
      correlation_group_id: string | null;
      correlated_events: Array<{
        id: number;
        camera_id: number;
        camera_name: string;
        timestamp: string;
        smart_detection_type: string | null;
        description: string;
        thumbnail_path: string | null;
      }>;
      total_correlated: number;
    }> => {
      const searchParams = new URLSearchParams();
      if (params?.limit) searchParams.set('limit', String(params.limit));
      const queryString = searchParams.toString();
      return apiFetch(`/events/${id}/correlated${queryString ? `?${queryString}` : ''}`);
    },

    // ========================================================================
    // Feedback endpoints (Story P4-5.1, P4-5.2)
    // ========================================================================

    /**
     * Submit feedback for an event's AI description (Story P4-5.1)
     * @param eventId Event ID
     * @param feedback Feedback data (rating, optional correction)
     * @returns Updated event with feedback
     */
    submitFeedback: async (eventId: number, feedback: { rating: 'helpful' | 'not_helpful'; correction?: string | null }): Promise<IEvent> => {
      return apiFetch(`/events/${eventId}/feedback`, {
        method: 'POST',
        body: JSON.stringify(feedback),
      });
    },

    /**
     * Get feedback statistics for analytics (Story P4-5.2)
     * @param params Optional filter parameters
     * @returns Aggregated feedback statistics
     */
    getFeedbackStats: async (params?: {
      camera_id?: number;
      days?: number;
    }): Promise<IFeedbackStats> => {
      const searchParams = new URLSearchParams();
      if (params?.camera_id) searchParams.set('camera_id', String(params.camera_id));
      if (params?.days) searchParams.set('days', String(params.days));
      const queryString = searchParams.toString();
      return apiFetch(`/events/feedback/stats${queryString ? `?${queryString}` : ''}`);
    },

    /**
     * Get prompt insights (Story P4-5.4)
     * @returns Prompt improvement suggestions
     */
    getPromptInsights: async (): Promise<IPromptInsightsResponse> => {
      return apiFetch('/events/feedback/prompt-insights');
    },

    /**
     * Apply a prompt suggestion (Story P4-5.4)
     * @param request The suggestion to apply
     * @returns Result of applying the suggestion
     */
    applyPromptSuggestion: async (request: IApplySuggestionRequest): Promise<IApplySuggestionResponse> => {
      return apiFetch('/events/feedback/apply-suggestion', {
        method: 'POST',
        body: JSON.stringify(request),
      });
    },

    /**
     * Get A/B test results (Story P4-5.4)
     * @returns A/B test comparison data
     */
    getABTestResults: async (): Promise<IABTestResultsResponse> => {
      return apiFetch('/events/feedback/ab-test-results');
    },

    /**
     * Get prompt history (Story P4-5.4)
     * @param params Optional pagination parameters
     * @returns List of prompt versions and their performance
     */
    getPromptHistory: async (params?: {
      limit?: number;
      offset?: number;
    }): Promise<IPromptHistoryResponse> => {
      const searchParams = new URLSearchParams();
      if (params?.limit) searchParams.set('limit', String(params.limit));
      if (params?.offset) searchParams.set('offset', String(params.offset));
      const queryString = searchParams.toString();
      return apiFetch(`/events/feedback/prompt-history${queryString ? `?${queryString}` : ''}`);
    },

    /**
     * Re-analyze an event with a different analysis mode (Story P3-6.4)
     * @param eventId Event ID (UUID string) to re-analyze
     * @param analysisMode New analysis mode to use
     * @returns Updated event with new analysis
     */
    reanalyze: async (eventId: string, analysisMode: string): Promise<IEvent> => {
      return apiFetch(`/events/${eventId}/reanalyze`, {
        method: 'POST',
        body: JSON.stringify({ analysis_mode: analysisMode }),
      });
    },

    /**
     * Get today's package deliveries summary (Story P7-2.4)
     * Returns total count, breakdown by carrier, and recent 5 events
     * @returns Package delivery summary for dashboard widget
     */
    getPackageDeliveriesToday: async (): Promise<{
      total_count: number;
      by_carrier: Record<string, number>;
      recent_events: Array<{
        id: string;
        timestamp: string;
        delivery_carrier: string | null;
        delivery_carrier_display: string;
        camera_name: string;
        thumbnail_path: string | null;
      }>;
    }> => {
      return apiFetch('/events/packages/today');
    },
  },

  settings: {
    /**
     * Get system settings
     */
    get: async (): Promise<SystemSettings> => {
      return apiFetch('/system/settings');
    },

    /**
     * Update system settings
     */
    update: async (settings: Partial<SystemSettings>): Promise<SystemSettings> => {
      return apiFetch('/system/settings', {
        method: 'PUT',
        body: JSON.stringify(settings),
      });
    },

    /**
     * Get storage statistics
     */
    storage: async (): Promise<StorageStats> => {
      return apiFetch('/system/storage');
    },

    /**
     * Test AI API key
     */
    testAIKey: async (request: AIKeyTestRequest): Promise<AIKeyTestResponse> => {
      return apiFetch('/ai/test-key', {
        method: 'POST',
        body: JSON.stringify(request),
      });
    },

    /**
     * Delete all event data
     */
    deleteAllData: async (): Promise<DeleteDataResponse> => {
      return apiFetch('/system/data', {
        method: 'DELETE',
      });
    },

    /**
     * Get AI usage statistics (Story P3-3.2)
     */
    getAIUsage: async (params?: IAIUsageQueryParams): Promise<IAIUsageResponse> => {
      const searchParams = new URLSearchParams();
      if (params?.days) searchParams.set('days', String(params.days));
      if (params?.provider) searchParams.set('provider', params.provider);
      if (params?.camera_id) searchParams.set('camera_id', String(params.camera_id));
      const queryString = searchParams.toString();
      return apiFetch(`/ai/usage${queryString ? `?${queryString}` : ''}`);
    },

    /**
     * Get cost cap status (Story P3-3.4)
     */
    getCostCapStatus: async (): Promise<ICostCapStatus> => {
      return apiFetch('/ai/cost-cap/status');
    },

    /**
     * Get AI providers configuration status (Story P2-5.2)
     */
    getAIProvidersStatus: async (): Promise<{
      providers: Array<{ provider: string; configured: boolean }>;
      order: string[];
    }> => {
      return apiFetch('/system/ai-providers');
    },
  },

  alertRules: {
    /**
     * List all alert rules
     */
    list: async (): Promise<IAlertRuleListResponse> => {
      return apiFetch('/alert-rules');
    },

    /**
     * Get single alert rule
     */
    get: async (id: number): Promise<IAlertRule> => {
      return apiFetch(`/alert-rules/${id}`);
    },

    /**
     * Create alert rule
     */
    create: async (rule: IAlertRuleCreate): Promise<IAlertRule> => {
      return apiFetch('/alert-rules', {
        method: 'POST',
        body: JSON.stringify(rule),
      });
    },

    /**
     * Update alert rule
     */
    update: async (id: number, rule: IAlertRuleUpdate): Promise<IAlertRule> => {
      return apiFetch(`/alert-rules/${id}`, {
        method: 'PUT',
        body: JSON.stringify(rule),
      });
    },

    /**
     * Delete alert rule
     */
    delete: async (id: number): Promise<void> => {
      return apiFetch(`/alert-rules/${id}`, {
        method: 'DELETE',
      });
    },

    /**
     * Toggle alert rule enabled status
     */
    toggle: async (id: number, enabled: boolean): Promise<IAlertRule> => {
      return apiFetch(`/alert-rules/${id}/toggle`, {
        method: 'PATCH',
        body: JSON.stringify({ enabled }),
      });
    },

    /**
     * Test alert rule against recent events
     */
    test: async (ruleId: string, request?: IAlertRuleTestRequest): Promise<IAlertRuleTestResponse> => {
      return apiFetch(`/alert-rules/${ruleId}/test`, {
        method: 'POST',
        body: request ? JSON.stringify(request) : undefined,
      });
    },

    /**
     * Test webhook delivery (Story P1-3.4)
     */
    testWebhook: async (request: IWebhookTestRequest): Promise<IWebhookTestResponse> => {
      return apiFetch('/alert-rules/test-webhook', {
        method: 'POST',
        body: JSON.stringify(request),
      });
    },

    /**
     * Get webhook delivery logs (Story P1-3.5)
     */
    getWebhookLogs: async (filters?: IWebhookLogsFilter): Promise<IWebhookLogsResponse> => {
      const params = new URLSearchParams();
      if (filters?.rule_id !== undefined) params.set('rule_id', String(filters.rule_id));
      if (filters?.success !== undefined) params.set('success', String(filters.success));
      if (filters?.offset !== undefined) params.set('skip', String(filters.offset));
      if (filters?.limit !== undefined) params.set('limit', String(filters.limit));
      const queryString = params.toString();
      return apiFetch(`/alert-rules/webhook-logs${queryString ? `?${queryString}` : ''}`);
    },

    /**
     * Retry a failed webhook delivery (Story P1-3.5)
     */
    retryWebhook: async (logId: number): Promise<IWebhookTestResponse> => {
      return apiFetch(`/alert-rules/webhook-logs/${logId}/retry`, {
        method: 'POST',
      });
    },

    /**
     * Export webhook logs as CSV (placeholder - not yet implemented in backend)
     */
    exportWebhookLogs: async (filters?: IWebhookLogsFilter): Promise<Blob> => {
      const params = new URLSearchParams();
      if (filters?.rule_id !== undefined) params.set('rule_id', String(filters.rule_id));
      if (filters?.success !== undefined) params.set('success', String(filters.success));
      if (filters?.start_date !== undefined) params.set('start_date', filters.start_date);
      if (filters?.end_date !== undefined) params.set('end_date', filters.end_date);
      const queryString = params.toString();
      const response = await fetch(`${API_BASE_URL}${API_V1_PREFIX}/alert-rules/webhook-logs/export${queryString ? `?${queryString}` : ''}`, {
        method: 'GET',
        headers: getAuthHeaders(),
      });
      if (!response.ok) {
        throw new ApiError('Failed to export webhook logs', response.status);
      }
      return response.blob();
    },
  },

  notifications: {
    /**
     * List notifications with optional filters
     */
    list: async (filters?: {
      unread_only?: boolean;
      skip?: number;
      limit?: number;
    }): Promise<INotificationListResponse> => {
      const params = new URLSearchParams();
      if (filters?.unread_only) params.set('unread_only', 'true');
      if (filters?.skip !== undefined) params.set('skip', String(filters.skip));
      if (filters?.limit !== undefined) params.set('limit', String(filters.limit));
      const queryString = params.toString();
      return apiFetch(`/notifications${queryString ? `?${queryString}` : ''}`);
    },

    /**
     * Get single notification
     */
    get: async (id: number): Promise<INotification> => {
      return apiFetch(`/notifications/${id}`);
    },

    /**
     * Mark notification as read
     */
    markRead: async (id: number): Promise<IMarkReadResponse> => {
      return apiFetch(`/notifications/${id}/read`, {
        method: 'POST',
      });
    },

    /**
     * Mark all notifications as read
     */
    markAllRead: async (): Promise<IMarkReadResponse> => {
      return apiFetch('/notifications/read-all', {
        method: 'POST',
      });
    },

    /**
     * Delete notification
     */
    delete: async (id: number): Promise<IDeleteNotificationResponse> => {
      return apiFetch(`/notifications/${id}`, {
        method: 'DELETE',
      });
    },

    /**
     * Delete all notifications
     */
    deleteAll: async (): Promise<IBulkDeleteResponse> => {
      return apiFetch('/notifications', {
        method: 'DELETE',
      });
    },

    /**
     * Get unread count
     */
    getUnreadCount: async (): Promise<{ count: number }> => {
      return apiFetch('/notifications/unread-count');
    },
  },

  monitoring: {
    /**
     * Get system health status
     */
    health: async (): Promise<SystemHealth> => {
      return apiFetch('/system/health');
    },

    /**
     * Get system logs
     */
    logs: async (params?: LogsQueryParams): Promise<LogsResponse> => {
      const searchParams = new URLSearchParams();
      if (params?.level) searchParams.set('level', params.level);
      if (params?.source) searchParams.set('source', params.source);
      if (params?.limit !== undefined) searchParams.set('limit', String(params.limit));
      if (params?.offset !== undefined) searchParams.set('offset', String(params.offset));
      if (params?.search) searchParams.set('search', params.search);
      if (params?.start_time) searchParams.set('start_time', params.start_time);
      if (params?.end_time) searchParams.set('end_time', params.end_time);
      const queryString = searchParams.toString();
      return apiFetch(`/system/logs${queryString ? `?${queryString}` : ''}`);
    },

    /**
     * Get available log files for download
     */
    logFiles: async (): Promise<LogFilesResponse> => {
      return apiFetch('/system/logs/files');
    },

    /**
     * Get download URL for a log file
     */
    getLogFileUrl: (filename: string): string => {
      return `${API_BASE_URL}${API_V1_PREFIX}/system/logs/files/${encodeURIComponent(filename)}`;
    },

    /**
     * Download logs as a file
     */
    downloadLogs: async (_params?: LogsQueryParams, source?: string): Promise<Blob> => {
      const filename = source ? `${source}.log` : 'app.log';
      const response = await fetch(`${API_BASE_URL}${API_V1_PREFIX}/system/logs/files/${encodeURIComponent(filename)}`, {
        method: 'GET',
        headers: getAuthHeaders(),
      });
      if (!response.ok) {
        throw new ApiError('Failed to download logs', response.status);
      }
      return response.blob();
    },
  },

  auth: {
    /**
     * Login with username and password
     * @param request Login credentials
     * @returns Login response with token
     */
    login: async (request: ILoginRequest): Promise<ILoginResponse> => {
      return apiFetch('/auth/login', {
        method: 'POST',
        body: JSON.stringify(request),
      });
    },

    /**
     * Logout current user
     * @returns Success message
     */
    logout: async (): Promise<IMessageResponse> => {
      return apiFetch('/auth/logout', {
        method: 'POST',
      });
    },

    /**
     * Get current user profile
     * @returns Current user data
     */
    me: async (): Promise<IUser> => {
      return apiFetch('/auth/me');
    },

    /**
     * Change current user's password
     * @param request Password change request
     * @returns Success message
     */
    changePassword: async (request: IChangePasswordRequest): Promise<IMessageResponse> => {
      return apiFetch('/auth/change-password', {
        method: 'POST',
        body: JSON.stringify(request),
      });
    },

    /**
     * Get initial setup status
     * @returns Setup status
     */
    getSetupStatus: async (): Promise<ISetupStatusResponse> => {
      return apiFetch('/auth/setup-status');
    },

    /**
     * Complete initial setup with admin credentials
     * @param request Admin setup request (username, password)
     * @returns Login response with token
     */
    completeSetup: async (request: { username: string; password: string }): Promise<ILoginResponse> => {
      return apiFetch('/auth/setup', {
        method: 'POST',
        body: JSON.stringify(request),
      });
    },
  },

  backup: {
    /**
     * Create a new backup
     * @param options Optional backup configuration
     * @returns Backup creation result
     */
    create: async (options?: IBackupOptions): Promise<IBackupResponse> => {
      return apiFetch('/backup', {
        method: 'POST',
        body: JSON.stringify(options || {}),
      });
    },

    /**
     * List all available backups
     * @returns List of backup files with metadata
     */
    list: async (): Promise<IBackupListResponse> => {
      return apiFetch('/backup');
    },

    /**
     * Validate a backup file before restore
     * @param fileOrFilename File object (uploaded) or filename (existing on server)
     * @returns Validation result with backup metadata
     */
    validate: async (fileOrFilename: File | string): Promise<IValidationResponse> => {
      if (typeof fileOrFilename === 'string') {
        return apiFetch(`/backup/${encodeURIComponent(fileOrFilename)}/validate`);
      }
      // Upload file for validation
      const formData = new FormData();
      formData.append('file', fileOrFilename);
      const response = await fetch(`${API_BASE_URL}${API_V1_PREFIX}/backup/validate`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: formData,
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new ApiError(errorData.detail || 'Validation failed', response.status);
      }
      return response.json();
    },

    /**
     * Restore from a backup file
     * @param fileOrFilename File object (uploaded) or filename (existing on server)
     * @param options Optional restore configuration
     * @returns Restore result
     */
    restore: async (fileOrFilename: File | string, options?: IRestoreOptions): Promise<IRestoreResponse> => {
      if (typeof fileOrFilename === 'string') {
        return apiFetch(`/backup/${encodeURIComponent(fileOrFilename)}/restore`, {
          method: 'POST',
          body: JSON.stringify(options || {}),
        });
      }
      // Upload file for restore
      const formData = new FormData();
      formData.append('file', fileOrFilename);
      if (options?.restore_database !== undefined) {
        formData.append('restore_database', String(options.restore_database));
      }
      if (options?.restore_thumbnails !== undefined) {
        formData.append('restore_thumbnails', String(options.restore_thumbnails));
      }
      if (options?.restore_settings !== undefined) {
        formData.append('restore_settings', String(options.restore_settings));
      }
      const response = await fetch(`${API_BASE_URL}${API_V1_PREFIX}/restore`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: formData,
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new ApiError(errorData.detail || 'Restore failed', response.status);
      }
      return response.json();
    },

    /**
     * Delete a backup file
     * @param filename Name of backup file to delete
     * @returns Deletion result
     */
    delete: async (filename: string): Promise<{ success: boolean; message: string }> => {
      return apiFetch(`/backup/${encodeURIComponent(filename)}`, {
        method: 'DELETE',
      });
    },

    /**
     * Get download URL for a backup file
     * @param filename Name of backup file
     * @returns Download URL
     */
    getDownloadUrl: (filename: string): string => {
      return `${API_BASE_URL}${API_V1_PREFIX}/backup/${encodeURIComponent(filename)}/download`;
    },

    /**
     * Download a backup file as blob
     * @param filename Name of backup file
     * @returns Backup file blob
     */
    download: async (filename: string): Promise<Blob> => {
      const response = await fetch(`${API_BASE_URL}${API_V1_PREFIX}/backup/${encodeURIComponent(filename)}/download`, {
        method: 'GET',
        headers: getAuthHeaders(),
      });
      if (!response.ok) {
        throw new ApiError('Failed to download backup', response.status);
      }
      return response.blob();
    },
  },

  discovery: {
    /**
     * Start network camera discovery
     * @returns Discovery session info
     */
    start: async (): Promise<IDiscoveryResponse> => {
      return apiFetch('/discovery/start', {
        method: 'POST',
      });
    },

    /**
     * Get current discovery status and results
     * @returns Discovery status with found devices
     */
    status: async (): Promise<IDiscoveryStatusResponse> => {
      return apiFetch('/discovery/status');
    },

    /**
     * Get detailed device information
     * @param address Device IP address
     * @returns Detailed device info
     */
    getDeviceDetails: async (address: string): Promise<IDeviceDetailsResponse> => {
      return apiFetch(`/discovery/device/${encodeURIComponent(address)}`);
    },

    /**
     * Test RTSP connection with credentials
     * @param address Device IP address
     * @param credentials Optional credentials
     * @returns Connection test result
     */
    testConnection: async (
      address: string,
      credentials?: { username?: string; password?: string; port?: number }
    ): Promise<ITestConnectionResponse> => {
      const params = new URLSearchParams();
      if (credentials?.username) params.set('username', credentials.username);
      if (credentials?.password) params.set('password', credentials.password);
      if (credentials?.port) params.set('port', String(credentials.port));
      const queryString = params.toString();
      return apiFetch(`/discovery/device/${encodeURIComponent(address)}/test${queryString ? `?${queryString}` : ''}`, {
        method: 'POST',
      });
    },

    /**
     * Import discovered camera
     * @param address Device IP address
     * @param options Import configuration
     * @returns Imported camera
     */
    importCamera: async (
      address: string,
      options: {
        name: string;
        username?: string;
        password?: string;
        rtsp_url?: string;
        enable_motion_detection?: boolean;
      }
    ): Promise<ICamera> => {
      return apiFetch(`/discovery/device/${encodeURIComponent(address)}/import`, {
        method: 'POST',
        body: JSON.stringify(options),
      });
    },
  },

  protect: {
    /**
     * Get all UniFi Protect controllers
     * @returns List of configured controllers
     */
    listControllers: async (): Promise<Array<{
      id: number;
      name: string;
      host: string;
      port: number;
      use_ssl: boolean;
      verify_ssl: boolean;
      enabled: boolean;
      is_connected: boolean;
      last_connected_at: string | null;
      last_error: string | null;
      connection_error: string | null;
      camera_count: number;
      created_at: string;
      updated_at: string | null;
    }>> => {
      return apiFetch('/protect/controllers');
    },

    /**
     * Get single controller by ID
     * @param id Controller ID
     * @returns Controller details
     */
    getController: async (id: number): Promise<{
      id: number;
      name: string;
      host: string;
      port: number;
      use_ssl: boolean;
      verify_ssl: boolean;
      enabled: boolean;
      is_connected: boolean;
      last_connected_at: string | null;
      last_error: string | null;
      connection_error: string | null;
      camera_count: number;
      created_at: string;
      updated_at: string | null;
    }> => {
      return apiFetch(`/protect/controllers/${id}`);
    },

    /**
     * Create new UniFi Protect controller
     * @param data Controller configuration
     * @returns Created controller
     */
    createController: async (data: {
      name: string;
      host: string;
      port?: number;
      username: string;
      password: string;
      use_ssl?: boolean;
      verify_ssl?: boolean;
      enabled?: boolean;
    }): Promise<{
      id: number;
      name: string;
      host: string;
      port: number;
      use_ssl: boolean;
      verify_ssl: boolean;
      enabled: boolean;
      is_connected: boolean;
      last_connected_at: string | null;
      last_error: string | null;
      connection_error: string | null;
      camera_count: number;
      created_at: string;
      updated_at: string | null;
    }> => {
      return apiFetch('/protect/controllers', {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },

    /**
     * Update existing UniFi Protect controller
     * @param id Controller ID
     * @param data Updated configuration
     * @returns Updated controller
     */
    updateController: async (id: number, data: {
      name?: string;
      host?: string;
      port?: number;
      username?: string;
      password?: string;
      use_ssl?: boolean;
      verify_ssl?: boolean;
      enabled?: boolean;
    }): Promise<{
      id: number;
      name: string;
      host: string;
      port: number;
      use_ssl: boolean;
      verify_ssl: boolean;
      enabled: boolean;
      is_connected: boolean;
      last_connected_at: string | null;
      last_error: string | null;
      connection_error: string | null;
      camera_count: number;
      created_at: string;
      updated_at: string | null;
    }> => {
      return apiFetch(`/protect/controllers/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      });
    },

    /**
     * Delete UniFi Protect controller
     * @param id Controller ID
     * @returns Deletion confirmation
     */
    deleteController: async (id: number): Promise<{ message: string }> => {
      return apiFetch(`/protect/controllers/${id}`, {
        method: 'DELETE',
      });
    },

    /**
     * Test connection to a Protect controller (before saving)
     * @param data Connection parameters
     * @returns Test result
     */
    testConnection: async (data: {
      host: string;
      port?: number;
      username: string;
      password: string;
      use_ssl?: boolean;
      verify_ssl?: boolean;
    }): Promise<{
      data: {
        success: boolean;
        message: string;
        firmware_version?: string;
        camera_count?: number;
      };
      meta: { request_id: string };
    }> => {
      return apiFetch('/protect/controllers/test', {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },

    /**
     * Test connection to an existing controller using stored credentials (Story P2-1.2)
     * @param id Controller ID
     * @returns Test result
     */
    testExistingController: async (id: number): Promise<{
      data: {
        success: boolean;
        message: string;
        firmware_version?: string;
        camera_count?: number;
      };
      meta: { request_id: string };
    }> => {
      return apiFetch(`/protect/controllers/${id}/test`, {
        method: 'POST',
      });
    },

    /**
     * Discover cameras from a Protect controller
     * @param id Controller ID
     * @returns List of discovered cameras
     */
    discoverCameras: async (id: number): Promise<{
      controller_id: number;
      cameras: ProtectDiscoveredCamera[];
    }> => {
      return apiFetch(`/protect/controllers/${id}/cameras`);
    },

    /**
     * Enable a Protect camera for AI processing
     * @param controllerId Controller ID
     * @param protectCameraId Protect camera ID
     * @returns Updated camera info
     */
    enableCamera: async (controllerId: number, protectCameraId: string): Promise<{
      protect_id: string;
      name: string;
      is_enabled_for_ai: boolean;
      message: string;
    }> => {
      return apiFetch(`/protect/controllers/${controllerId}/cameras/${protectCameraId}/enable`, {
        method: 'PUT',
      });
    },

    /**
     * Disable a Protect camera for AI processing
     * @param controllerId Controller ID
     * @param protectCameraId Protect camera ID
     * @returns Updated camera info
     */
    disableCamera: async (controllerId: number, protectCameraId: string): Promise<{
      protect_id: string;
      name: string;
      is_enabled_for_ai: boolean;
      message: string;
    }> => {
      return apiFetch(`/protect/controllers/${controllerId}/cameras/${protectCameraId}/disable`, {
        method: 'PUT',
      });
    },

    /**
     * Update event filters for a Protect camera
     * @param controllerId Controller ID
     * @param protectCameraId Protect camera ID
     * @param filters Event types to enable
     * @returns Updated camera info
     */
    updateEventFilters: async (
      controllerId: number,
      protectCameraId: string,
      filters: string[]
    ): Promise<{
      protect_id: string;
      name: string;
      event_filters: string[];
      message: string;
    }> => {
      return apiFetch(`/protect/controllers/${controllerId}/cameras/${protectCameraId}/filters`, {
        method: 'PUT',
        body: JSON.stringify({ event_filters: filters }),
      });
    },
  },

  // ============================================================================
  // MQTT Integration (Story P4-2)
  // ============================================================================
  mqtt: {
    /**
     * Get MQTT configuration
     * @returns Current MQTT configuration
     */
    getConfig: async (): Promise<MQTTConfigResponse> => {
      return apiFetch('/mqtt/config');
    },

    /**
     * Update MQTT configuration
     * @param config Updated configuration values
     * @returns Updated MQTT configuration
     */
    updateConfig: async (config: MQTTConfigUpdate): Promise<MQTTConfigResponse> => {
      return apiFetch('/mqtt/config', {
        method: 'PUT',
        body: JSON.stringify(config),
      });
    },

    /**
     * Get MQTT connection status
     * @returns Current connection status
     */
    getStatus: async (): Promise<MQTTStatusResponse> => {
      return apiFetch('/mqtt/status');
    },

    /**
     * Test MQTT connection
     * @param request Test connection parameters
     * @returns Test result
     */
    testConnection: async (request: MQTTTestRequest): Promise<MQTTTestResponse> => {
      return apiFetch('/mqtt/test', {
        method: 'POST',
        body: JSON.stringify(request),
      });
    },

    /**
     * Connect to MQTT broker
     * @returns Connection result
     */
    connect: async (): Promise<{ success: boolean; message: string }> => {
      return apiFetch('/mqtt/connect', {
        method: 'POST',
      });
    },

    /**
     * Disconnect from MQTT broker
     * @returns Disconnection result
     */
    disconnect: async (): Promise<{ success: boolean; message: string }> => {
      return apiFetch('/mqtt/disconnect', {
        method: 'POST',
      });
    },

    /**
     * Publish Home Assistant discovery config
     * @returns Discovery publish result
     */
    publishDiscovery: async (): Promise<MQTTPublishDiscoveryResponse> => {
      return apiFetch('/mqtt/discovery/publish', {
        method: 'POST',
      });
    },
  },

  // ============================================================================
  // HomeKit Integration (Story P4-6, P5-1, P7-1)
  // ============================================================================
  homekit: {
    /**
     * Get HomeKit bridge status
     * @returns Current HomeKit status including pairing info
     */
    getStatus: async (): Promise<{
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
    }> => {
      return apiFetch('/homekit/status');
    },

    /**
     * Enable or disable HomeKit integration
     * @param enabled Whether to enable HomeKit
     * @returns Updated status
     */
    setEnabled: async (enabled: boolean): Promise<{
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
    }> => {
      return apiFetch('/homekit/settings', {
        method: 'PUT',
        body: JSON.stringify({ enabled }),
      });
    },

    /**
     * Reset HomeKit pairing (generates new setup code)
     * @returns New setup code
     */
    resetPairing: async (): Promise<{
      success: boolean;
      message: string;
      new_setup_code: string | null;
    }> => {
      return apiFetch('/homekit/reset', {
        method: 'POST',
      });
    },

    /**
     * Get HomeKit pairings (Story P5-1.8)
     * @returns List of paired devices
     */
    getPairings: async (): Promise<{
      pairings: Array<{
        pairing_id: string;
        is_admin: boolean;
        permissions: number;
      }>;
      count: number;
    }> => {
      return apiFetch('/homekit/pairings');
    },

    /**
     * Remove a specific HomeKit pairing (Story P5-1.8)
     * @param pairingId The pairing ID to remove
     * @returns Removal result
     */
    removePairing: async (pairingId: string): Promise<{
      success: boolean;
      message: string;
      pairing_id: string;
    }> => {
      return apiFetch(`/homekit/pairings/${encodeURIComponent(pairingId)}`, {
        method: 'DELETE',
      });
    },

    /**
     * Get HomeKit diagnostics (Story P7-1.1, P7-1.4)
     * @returns Diagnostic information for troubleshooting
     */
    getDiagnostics: async (): Promise<{
      bridge_running: boolean;
      mdns_advertising: boolean;
      network_binding: { ip: string; port: number; interface?: string | null } | null;
      connected_clients: number;
      last_event_delivery: {
        camera_id: string;
        camera_name?: string | null;  // Story P7-1.4
        sensor_type: string;
        timestamp: string;
        delivered: boolean;
      } | null;
      sensor_deliveries: Array<{  // Story P7-1.4 AC3
        camera_id: string;
        camera_name?: string | null;
        sensor_type: string;
        timestamp: string;
        delivered: boolean;
      }>;
      recent_logs: Array<{
        timestamp: string;
        level: string;
        category: string;
        message: string;
        details?: Record<string, unknown>;
      }>;
      warnings: string[];
      errors: string[];
    }> => {
      return apiFetch('/homekit/diagnostics');
    },

    /**
     * Test HomeKit connectivity (Story P7-1.2)
     * @returns Connectivity test results including mDNS visibility and port accessibility
     */
    testConnectivity: async (): Promise<{
      mdns_visible: boolean;
      discovered_as: string | null;
      port_accessible: boolean;
      network_binding: { ip: string; port: number; interface?: string | null } | null;
      firewall_issues: string[];
      recommendations: string[];
      test_duration_ms: number;
    }> => {
      return apiFetch('/homekit/test-connectivity', {
        method: 'POST',
      });
    },

    /**
     * Trigger a test HomeKit event for debugging (Story P7-1.3)
     * @param request Contains camera_id and event_type to trigger
     * @returns Test event result with delivery confirmation
     */
    testEvent: async (request: {
      camera_id: string;
      event_type: 'motion' | 'occupancy' | 'vehicle' | 'animal' | 'package' | 'doorbell';
    }): Promise<{
      success: boolean;
      message: string;
      camera_id: string;
      event_type: string;
      sensor_name: string | null;
      delivered_to_clients: number;
      timestamp: string;
    }> => {
      return apiFetch('/homekit/test-event', {
        method: 'POST',
        body: JSON.stringify(request),
      });
    },
  },

  // ============================================================================
  // Entity Management (Story P4-3.6)
  // ============================================================================
  entities: {
    /**
     * Get all recognized entities with pagination and filtering
     * @param params Query parameters (limit, offset, entity_type, named_only)
     * @returns List of entities with total count
     */
    list: async (params?: {
      limit?: number;
      offset?: number;
      entity_type?: 'person' | 'vehicle' | 'unknown';
      named_only?: boolean;
    }): Promise<{
      entities: Array<{
        id: string;
        entity_type: string;
        name: string | null;
        first_seen_at: string;
        last_seen_at: string;
        occurrence_count: number;
      }>;
      total: number;
    }> => {
      const searchParams = new URLSearchParams();
      if (params?.limit) searchParams.set('limit', String(params.limit));
      if (params?.offset) searchParams.set('offset', String(params.offset));
      if (params?.entity_type) searchParams.set('entity_type', params.entity_type);
      if (params?.named_only) searchParams.set('named_only', 'true');

      const queryString = searchParams.toString();
      return apiFetch(`/context/entities${queryString ? `?${queryString}` : ''}`);
    },

    /**
     * Get a single entity by ID
     * @param id Entity ID
     * @returns Entity details with recent events
     */
    get: async (id: string): Promise<{
      id: string;
      entity_type: string;
      name: string | null;
      first_seen_at: string;
      last_seen_at: string;
      occurrence_count: number;
      created_at?: string;
      updated_at?: string;
      recent_events: Array<{
        id: string;
        timestamp: string;
        description: string;
        thumbnail_url: string | null;
        camera_id: string;
        similarity_score: number;
      }>;
    }> => {
      return apiFetch(`/context/entities/${encodeURIComponent(id)}`);
    },

    /**
     * Update entity (assign name or type)
     * @param id Entity ID
     * @param data Updated entity data
     * @returns Updated entity
     */
    update: async (id: string, data: {
      name?: string | null;
      entity_type?: 'person' | 'vehicle' | 'unknown';
    }): Promise<{
      id: string;
      entity_type: string;
      name: string | null;
      first_seen_at: string;
      last_seen_at: string;
      occurrence_count: number;
    }> => {
      return apiFetch(`/context/entities/${encodeURIComponent(id)}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      });
    },

    /**
     * Delete entity
     * @param id Entity ID
     * @returns Deletion confirmation
     */
    delete: async (id: string): Promise<{ message: string }> => {
      return apiFetch(`/context/entities/${encodeURIComponent(id)}`, {
        method: 'DELETE',
      });
    },

    /**
     * Merge two entities (Story P4-3.6)
     * @param sourceId Source entity ID (will be merged into target)
     * @param targetId Target entity ID (will remain)
     * @returns Merged entity
     */
    merge: async (sourceId: string, targetId: string): Promise<{
      merged_entity: {
        id: string;
        entity_type: string;
        name: string | null;
        first_seen_at: string;
        last_seen_at: string;
        occurrence_count: number;
      };
      message: string;
    }> => {
      return apiFetch(`/context/entities/${encodeURIComponent(sourceId)}/merge`, {
        method: 'POST',
        body: JSON.stringify({ target_id: targetId }),
      });
    },
  },

  // ============================================================================
  // Push Notifications (Story P4-1)
  // ============================================================================
  push: {
    /**
     * Get VAPID public key for push subscription
     * @returns VAPID public key
     */
    getVapidPublicKey: async (): Promise<{
      public_key: string;
    }> => {
      return apiFetch('/push/vapid-public-key');
    },

    /**
     * Subscribe to push notifications
     * @param subscription Push subscription data
     * @returns Subscription confirmation
     */
    subscribe: async (subscription: {
      endpoint: string;
      keys: {
        p256dh: string;
        auth: string;
      };
      device_name?: string;
    }): Promise<{
      success: boolean;
      message: string;
      subscription_id: string;
    }> => {
      return apiFetch('/push/subscribe', {
        method: 'POST',
        body: JSON.stringify(subscription),
      });
    },

    /**
     * Unsubscribe from push notifications
     * @param endpoint Push subscription endpoint
     * @returns Unsubscription confirmation
     */
    unsubscribe: async (endpoint: string): Promise<{
      success: boolean;
      message: string;
    }> => {
      return apiFetch('/push/unsubscribe', {
        method: 'POST',
        body: JSON.stringify({ endpoint }),
      });
    },

    /**
     * List all push subscriptions
     * @returns List of subscriptions
     */
    listSubscriptions: async (): Promise<{
      subscriptions: Array<{
        id: string;
        device_name: string | null;
        created_at: string;
        last_used_at: string | null;
      }>;
    }> => {
      return apiFetch('/push/subscriptions');
    },

    /**
     * Delete a push subscription by ID
     * @param id Subscription ID
     * @returns Deletion confirmation
     */
    deleteSubscription: async (id: string): Promise<{
      success: boolean;
      message: string;
    }> => {
      return apiFetch(`/push/subscriptions/${encodeURIComponent(id)}`, {
        method: 'DELETE',
      });
    },

    /**
     * Test push notification delivery
     * @returns Test result
     */
    testNotification: async (): Promise<{
      success: boolean;
      message: string;
      subscriptions_notified: number;
    }> => {
      return apiFetch('/push/test', {
        method: 'POST',
      });
    },

    /**
     * Get notification preferences for a subscription (Story P4-1.4)
     * @param endpoint Push subscription endpoint
     * @returns Notification preferences
     */
    getPreferences: async (endpoint: string): Promise<{
      id: string;
      subscription_id: string;
      enabled_cameras: string[] | null;
      enabled_object_types: string[] | null;
      quiet_hours_enabled: boolean;
      quiet_hours_start: string | null;
      quiet_hours_end: string | null;
      timezone: string;
      sound_enabled: boolean;
      created_at: string | null;
      updated_at: string | null;
    }> => {
      return apiFetch('/push/preferences', {
        method: 'POST',
        body: JSON.stringify({ endpoint }),
      });
    },

    /**
     * Update notification preferences for a subscription (Story P4-1.4)
     * @param request Preference update request
     * @returns Updated preferences
     */
    updatePreferences: async (request: {
      endpoint: string;
      enabled_cameras?: string[] | null;
      enabled_object_types?: string[] | null;
      quiet_hours_enabled: boolean;
      quiet_hours_start?: string | null;
      quiet_hours_end?: string | null;
      timezone: string;
      sound_enabled: boolean;
    }): Promise<{
      id: string;
      subscription_id: string;
      enabled_cameras: string[] | null;
      enabled_object_types: string[] | null;
      quiet_hours_enabled: boolean;
      quiet_hours_start: string | null;
      quiet_hours_end: string | null;
      timezone: string;
      sound_enabled: boolean;
      created_at: string | null;
      updated_at: string | null;
    }> => {
      return apiFetch('/push/preferences', {
        method: 'PUT',
        body: JSON.stringify(request),
      });
    },
  },

  // ============================================================================
  // Activity Summaries (Story P4-4.4, P4-4.5)
  // ============================================================================
  summaries: {
    /**
     * Get recent summaries (today and yesterday)
     * @returns Recent summaries for dashboard display
     */
    recent: async (): Promise<RecentSummariesResponse> => {
      return apiFetch('/summaries/recent');
    },

    /**
     * Generate an on-demand summary
     * @param params Generation parameters
     * @returns Generated summary
     */
    generate: async (params: SummaryGenerateRequest): Promise<SummaryGenerateResponse> => {
      return apiFetch('/summaries/generate', {
        method: 'POST',
        body: JSON.stringify(params),
      });
    },

    /**
     * List summaries with pagination
     * @param limit Max summaries to return
     * @param offset Pagination offset
     * @returns Summary list
     */
    list: async (limit = 20, offset = 0): Promise<SummaryListResponse> => {
      return apiFetch(`/summaries?limit=${limit}&offset=${offset}`);
    },
  },
};

// ============================================================================
// Exported Types for Activity Summaries (Story P4-4.4, P4-4.5)
// ============================================================================

export interface RecentSummaryItem {
  id: string;
  date: string;
  period: 'morning' | 'afternoon' | 'evening' | 'night' | 'daily';
  event_count: number;
  summary_text: string;
  highlights: string[];
  created_at: string;
  // Stats for display
  camera_count: number;
  alert_count: number;
  doorbell_count: number;
  person_count: number;
  vehicle_count: number;
}

export interface RecentSummariesResponse {
  summaries: RecentSummaryItem[];
  today: RecentSummaryItem | null;
  yesterday: RecentSummaryItem | null;
}

export interface SummaryGenerateRequest {
  hours_back?: number;
  start_time?: string;
  end_time?: string;
  camera_ids?: number[];
}

export interface SummaryGenerateResponse {
  id: string;
  summary_text: string;
  event_count: number;
  period_start: string;
  period_end: string;
  highlights: string[];
  created_at: string;
  provider_used?: string;
  // Stats for display
  camera_count: number;
  alert_count: number;
  doorbell_count: number;
  person_count: number;
  vehicle_count: number;
}

export interface SummaryStats {
  total_summaries: number;
  avg_events_per_summary: number;
}

export interface SummaryListResponse {
  summaries: RecentSummaryItem[];
  total: number;
  stats: SummaryStats;
}
