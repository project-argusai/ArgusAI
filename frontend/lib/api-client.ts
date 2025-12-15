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

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_V1_PREFIX = '/api/v1';

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
     * @param filters Optional filters (is_enabled)
     * @returns Array of cameras
     */
    list: async (filters?: { is_enabled?: boolean }): Promise<ICamera[]> => {
      const params = new URLSearchParams();
      if (filters?.is_enabled !== undefined) {
        params.append('is_enabled', String(filters.is_enabled));
      }

      const queryString = params.toString();
      const endpoint = `/cameras${queryString ? `?${queryString}` : ''}`;

      return apiFetch<ICamera[]>(endpoint);
    },

    /**
     * Get single camera by ID
     * @param id Camera UUID
     * @returns Camera object
     * @throws ApiError with 404 if not found
     */
    getById: async (id: string): Promise<ICamera> => {
      return apiFetch<ICamera>(`/cameras/${id}`);
    },

    /**
     * Create new camera
     * @param data Camera creation payload
     * @returns Created camera object
     * @throws ApiError with 400 for validation errors, 409 for duplicate name
     */
    create: async (data: ICameraCreate): Promise<ICamera> => {
      return apiFetch<ICamera>('/cameras', {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },

    /**
     * Update existing camera
     * @param id Camera UUID
     * @param data Partial camera update payload
     * @returns Updated camera object
     * @throws ApiError with 404 if not found, 400 for validation errors
     */
    update: async (id: string, data: ICameraUpdate): Promise<ICamera> => {
      return apiFetch<ICamera>(`/cameras/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      });
    },

    /**
     * Delete camera
     * @param id Camera UUID
     * @returns Success confirmation
     * @throws ApiError with 404 if not found
     */
    delete: async (id: string): Promise<{ deleted: boolean }> => {
      return apiFetch<{ deleted: boolean }>(`/cameras/${id}`, {
        method: 'DELETE',
      });
    },

    /**
     * Test camera connection
     * @param id Camera UUID
     * @returns Test result with optional thumbnail
     * @throws ApiError with 404 if not found
     */
    testConnection: async (id: string): Promise<ICameraTestResponse> => {
      return apiFetch<ICameraTestResponse>(`/cameras/${id}/test`, {
        method: 'POST',
      });
    },

    /**
     * Get camera preview thumbnail
     * @param id Camera UUID
     * @returns Preview thumbnail as base64 or path
     * @throws ApiError with 404 if not found
     */
    preview: async (id: string): Promise<{ thumbnail_base64?: string; thumbnail_path?: string }> => {
      return apiFetch<{ thumbnail_base64?: string; thumbnail_path?: string }>(`/cameras/${id}/preview`);
    },

    /**
     * Trigger manual camera analysis
     * @param id Camera UUID
     * @returns Success confirmation
     * @throws ApiError with 404 if not found
     */
    analyze: async (id: string): Promise<{ success: boolean; message?: string }> => {
      return apiFetch<{ success: boolean; message?: string }>(`/cameras/${id}/analyze`, {
        method: 'POST',
      });
    },
  },

  /**
   * Events API client
   */
  events: {
    /**
     * Get paginated events with optional filters
     * @param filters Event filters (search, camera, date range, objects, confidence)
     * @param pagination Pagination params (skip, limit)
     * @returns Paginated events response
     */
    list: async (
      filters?: IEventFilters,
      pagination?: { skip?: number; limit?: number }
    ): Promise<IEventsResponse> => {
      const params = new URLSearchParams();

      // Pagination
      if (pagination?.skip !== undefined) {
        params.append('skip', String(pagination.skip));
      }
      if (pagination?.limit !== undefined) {
        params.append('limit', String(pagination.limit));
      }

      // Filters
      if (filters?.search) {
        params.append('search', filters.search);
      }
      if (filters?.camera_id) {
        params.append('camera_id', filters.camera_id);
      }
      if (filters?.start_date) {
        params.append('start_date', filters.start_date);
      }
      if (filters?.end_date) {
        params.append('end_date', filters.end_date);
      }
      if (filters?.objects && filters.objects.length > 0) {
        params.append('objects', filters.objects.join(','));
      }
      if (filters?.min_confidence !== undefined) {
        params.append('min_confidence', String(filters.min_confidence));
      }
      if (filters?.source_type) {
        params.append('source_type', filters.source_type);
      }
      if (filters?.smart_detection_type) {
        params.append('smart_detection_type', filters.smart_detection_type);
      }
      // Story P3-7.6: Analysis mode filtering
      if (filters?.analysis_mode) {
        params.append('analysis_mode', filters.analysis_mode);
      }
      if (filters?.has_fallback !== undefined) {
        params.append('has_fallback', String(filters.has_fallback));
      }
      if (filters?.low_confidence !== undefined) {
        params.append('low_confidence', String(filters.low_confidence));
      }

      const queryString = params.toString();
      const endpoint = `/events${queryString ? `?${queryString}` : ''}`;

      return apiFetch<IEventsResponse>(endpoint);
    },

    /**
     * Get single event by ID
     * @param id Event UUID
     * @returns Event object
     * @throws ApiError with 404 if not found
     */
    getById: async (id: string): Promise<IEvent> => {
      return apiFetch<IEvent>(`/events/${id}`);
    },

    /**
     * Delete event by ID
     * @param id Event UUID
     * @returns void (204 No Content)
     * @throws ApiError with 404 if not found
     */
    delete: async (id: string): Promise<void> => {
      await apiFetch<void>(`/events/${id}`, {
        method: 'DELETE',
      });
    },

    /**
     * Delete multiple events by ID (FF-010)
     * @param ids Array of event UUIDs to delete
     * @returns Deletion statistics
     * @throws ApiError with 400 if no IDs provided or too many (>100)
     * @throws ApiError with 404 if no events found
     */
    bulkDelete: async (ids: string[]): Promise<{
      deleted_count: number;
      thumbnails_deleted: number;
      frames_deleted: number;
      space_freed_mb: number;
      not_found_count: number;
    }> => {
      const params = new URLSearchParams();
      ids.forEach(id => params.append('event_ids', id));
      return apiFetch(`/events/bulk?${params.toString()}`, {
        method: 'DELETE',
      });
    },

    /**
     * Re-analyze an event with a different analysis mode (Story P3-6.4)
     * @param id Event UUID
     * @param analysisMode Analysis mode to use: 'single_frame', 'multi_frame', 'video_native'
     * @returns Updated event with new description and confidence
     * @throws ApiError with 404 if event not found
     * @throws ApiError with 400 if analysis mode not available for camera type
     * @throws ApiError with 429 if rate limit exceeded (max 3 per hour)
     */
    reanalyze: async (id: string, analysisMode: 'single_frame' | 'multi_frame' | 'video_native'): Promise<IEvent> => {
      return apiFetch<IEvent>(`/events/${id}/reanalyze`, {
        method: 'POST',
        body: JSON.stringify({ analysis_mode: analysisMode }),
      });
    },

    /**
     * Submit feedback for an event (Story P4-5.1)
     * @param eventId Event UUID
     * @param data Feedback data with rating and optional correction
     * @returns Created feedback object
     * @throws ApiError with 404 if event not found
     * @throws ApiError with 409 if feedback already exists
     */
    submitFeedback: async (eventId: string, data: {
      rating: 'helpful' | 'not_helpful';
      correction?: string;
    }): Promise<IEventFeedback> => {
      return apiFetch<IEventFeedback>(`/events/${eventId}/feedback`, {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },

    /**
     * Get feedback for an event (Story P4-5.1)
     * @param eventId Event UUID
     * @returns Feedback object if exists
     * @throws ApiError with 404 if event or feedback not found
     */
    getFeedback: async (eventId: string): Promise<IEventFeedback> => {
      return apiFetch<IEventFeedback>(`/events/${eventId}/feedback`);
    },

    /**
     * Update feedback for an event (Story P4-5.1)
     * @param eventId Event UUID
     * @param data Updated feedback data
     * @returns Updated feedback object
     * @throws ApiError with 404 if event or feedback not found
     */
    updateFeedback: async (eventId: string, data: {
      rating?: 'helpful' | 'not_helpful';
      correction?: string;
    }): Promise<IEventFeedback> => {
      return apiFetch<IEventFeedback>(`/events/${eventId}/feedback`, {
        method: 'PUT',
        body: JSON.stringify(data),
      });
    },

    /**
     * Delete feedback for an event (Story P4-5.1)
     * @param eventId Event UUID
     * @throws ApiError with 404 if event or feedback not found
     */
    deleteFeedback: async (eventId: string): Promise<void> => {
      await apiFetch<void>(`/events/${eventId}/feedback`, {
        method: 'DELETE',
      });
    },
  },

  /**
   * Feedback Statistics API client (Story P4-5.2)
   */
  feedback: {
    /**
     * Get aggregate feedback statistics for AI description accuracy monitoring
     * @param params Optional filters: camera_id, start_date, end_date
     * @returns Aggregate feedback statistics including accuracy rates, per-camera breakdown, daily trends, and top corrections
     */
    getStats: async (params?: {
      camera_id?: string;
      start_date?: string;
      end_date?: string;
    }): Promise<IFeedbackStats> => {
      const queryParams = new URLSearchParams();
      if (params?.camera_id) queryParams.append('camera_id', params.camera_id);
      if (params?.start_date) queryParams.append('start_date', params.start_date);
      if (params?.end_date) queryParams.append('end_date', params.end_date);

      const queryString = queryParams.toString();
      const endpoint = `/feedback/stats${queryString ? `?${queryString}` : ''}`;

      return apiFetch<IFeedbackStats>(endpoint);
    },

    /**
     * Get prompt improvement suggestions based on feedback analysis (Story P4-5.4)
     * @param params Optional filter: camera_id
     * @returns Prompt insights with suggestions and camera-specific analysis
     */
    getPromptInsights: async (params?: {
      camera_id?: string;
    }): Promise<IPromptInsightsResponse> => {
      const queryParams = new URLSearchParams();
      if (params?.camera_id) queryParams.append('camera_id', params.camera_id);

      const queryString = queryParams.toString();
      const endpoint = `/feedback/prompt-insights${queryString ? `?${queryString}` : ''}`;

      return apiFetch<IPromptInsightsResponse>(endpoint);
    },

    /**
     * Apply a prompt suggestion (Story P4-5.4)
     * @param data Suggestion ID and optional camera ID
     * @returns Result with new prompt and version
     */
    applySuggestion: async (data: IApplySuggestionRequest): Promise<IApplySuggestionResponse> => {
      return apiFetch<IApplySuggestionResponse>('/feedback/prompt-insights/apply', {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },

    /**
     * Get A/B test results (Story P4-5.4)
     * @param params Optional date range filters
     * @returns A/B test statistics with winner determination
     */
    getABTestResults: async (params?: {
      start_date?: string;
      end_date?: string;
    }): Promise<IABTestResultsResponse> => {
      const queryParams = new URLSearchParams();
      if (params?.start_date) queryParams.append('start_date', params.start_date);
      if (params?.end_date) queryParams.append('end_date', params.end_date);

      const queryString = queryParams.toString();
      const endpoint = `/feedback/ab-test/results${queryString ? `?${queryString}` : ''}`;

      return apiFetch<IABTestResultsResponse>(endpoint);
    },

    /**
     * Get prompt history (Story P4-5.4)
     * @param params Optional filter: camera_id, limit
     * @returns Prompt history entries
     */
    getPromptHistory: async (params?: {
      camera_id?: string;
      limit?: number;
    }): Promise<IPromptHistoryResponse> => {
      const queryParams = new URLSearchParams();
      if (params?.camera_id) queryParams.append('camera_id', params.camera_id);
      if (params?.limit) queryParams.append('limit', params.limit.toString());

      const queryString = queryParams.toString();
      const endpoint = `/feedback/prompt-history${queryString ? `?${queryString}` : ''}`;

      return apiFetch<IPromptHistoryResponse>(endpoint);
    },
  },

  /**
   * Settings API client
   */
  settings: {
    /**
     * Get all system settings
     * @returns System settings object
     */
    get: async (): Promise<SystemSettings> => {
      return apiFetch<SystemSettings>('/system/settings');
    },

    /**
     * Update system settings (partial update)
     * @param data Partial settings update payload
     * @returns Updated settings object
     */
    update: async (data: Partial<SystemSettings>): Promise<SystemSettings> => {
      return apiFetch<SystemSettings>('/system/settings', {
        method: 'PUT',
        body: JSON.stringify(data),
      });
    },

    /**
     * Test AI API key
     * @param data Provider and API key to test
     * @returns Test result with validation status
     */
    testApiKey: async (data: AIKeyTestRequest): Promise<AIKeyTestResponse> => {
      return apiFetch<AIKeyTestResponse>('/system/test-key', {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },

    /**
     * Get AI providers status (Story P2-5.2)
     * @returns List of providers with configuration status and order
     */
    getAIProvidersStatus: async (): Promise<{
      providers: Array<{ provider: string; configured: boolean }>;
      order: string[];
    }> => {
      return apiFetch<{
        providers: Array<{ provider: string; configured: boolean }>;
        order: string[];
      }>('/system/ai-providers');
    },

    /**
     * Get storage statistics
     * @returns Storage usage information
     */
    getStorageStats: async (): Promise<StorageStats> => {
      return apiFetch<StorageStats>('/system/storage');
    },

    /**
     * Export all events
     * @param format Export format (json or csv)
     * @returns Blob for download
     */
    exportData: async (format: 'json' | 'csv' = 'json'): Promise<Blob> => {
      const url = `${API_BASE_URL}${API_V1_PREFIX}/events/export?format=${format}`;
      const headers: HeadersInit = {};
      const token = getAuthToken();
      if (token) {
        (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
      }
      const response = await fetch(url, { headers });
      if (!response.ok) {
        throw new ApiError(`Failed to export data`, response.status);
      }
      return response.blob();
    },

    /**
     * Delete all event data
     * @returns Deletion result
     */
    deleteAllData: async (): Promise<DeleteDataResponse> => {
      return apiFetch<DeleteDataResponse>('/events', {
        method: 'DELETE',
      });
    },

    /**
     * Get AI usage statistics (Story P3-7.2)
     * @param params Optional start_date and end_date in YYYY-MM-DD format
     * @returns AI usage aggregation with breakdown by date, camera, provider, and mode
     */
    getAIUsage: async (params?: IAIUsageQueryParams): Promise<IAIUsageResponse> => {
      const searchParams = new URLSearchParams();
      if (params?.start_date) {
        searchParams.append('start_date', params.start_date);
      }
      if (params?.end_date) {
        searchParams.append('end_date', params.end_date);
      }
      const queryString = searchParams.toString();
      const endpoint = `/system/ai-usage${queryString ? `?${queryString}` : ''}`;
      return apiFetch<IAIUsageResponse>(endpoint);
    },

    /**
     * Get AI cost cap status (Story P3-7.3)
     * @returns Current cost cap status including daily/monthly costs, caps, and pause state
     */
    getCostCapStatus: async (): Promise<ICostCapStatus> => {
      return apiFetch<ICostCapStatus>('/system/ai-cost-status');
    },

    /**
     * Update cost cap settings (Story P3-7.3)
     * @param caps Object with daily_cap and/or monthly_cap (null for no limit)
     * @returns Updated settings
     */
    updateCostCaps: async (caps: {
      ai_daily_cost_cap?: number | null;
      ai_monthly_cost_cap?: number | null;
    }): Promise<SystemSettings> => {
      return apiFetch<SystemSettings>('/system/settings', {
        method: 'PUT',
        body: JSON.stringify(caps),
      });
    },
  },

  /**
   * Alert Rules API client (Epic 5)
   */
  alertRules: {
    /**
     * Get all alert rules
     * @param filters Optional filters (is_enabled)
     * @returns Paginated list of alert rules
     */
    list: async (filters?: { is_enabled?: boolean }): Promise<IAlertRuleListResponse> => {
      const params = new URLSearchParams();
      if (filters?.is_enabled !== undefined) {
        params.append('is_enabled', String(filters.is_enabled));
      }

      const queryString = params.toString();
      const endpoint = `/alert-rules${queryString ? `?${queryString}` : ''}`;

      return apiFetch<IAlertRuleListResponse>(endpoint);
    },

    /**
     * Get single alert rule by ID
     * @param id Alert rule UUID
     * @returns Alert rule object
     * @throws ApiError with 404 if not found
     */
    getById: async (id: string): Promise<IAlertRule> => {
      return apiFetch<IAlertRule>(`/alert-rules/${id}`);
    },

    /**
     * Create new alert rule
     * @param data Alert rule creation payload
     * @returns Created alert rule object
     * @throws ApiError with 422 for validation errors
     */
    create: async (data: IAlertRuleCreate): Promise<IAlertRule> => {
      return apiFetch<IAlertRule>('/alert-rules', {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },

    /**
     * Update existing alert rule
     * @param id Alert rule UUID
     * @param data Partial alert rule update payload
     * @returns Updated alert rule object
     * @throws ApiError with 404 if not found, 422 for validation errors
     */
    update: async (id: string, data: IAlertRuleUpdate): Promise<IAlertRule> => {
      return apiFetch<IAlertRule>(`/alert-rules/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      });
    },

    /**
     * Delete alert rule
     * @param id Alert rule UUID
     * @throws ApiError with 404 if not found
     */
    delete: async (id: string): Promise<void> => {
      await apiFetch<void>(`/alert-rules/${id}`, {
        method: 'DELETE',
      });
    },

    /**
     * Test alert rule against historical events
     * @param id Alert rule UUID
     * @param data Optional test parameters
     * @returns Test results with matching event IDs
     * @throws ApiError with 404 if not found
     */
    test: async (id: string, data?: IAlertRuleTestRequest): Promise<IAlertRuleTestResponse> => {
      return apiFetch<IAlertRuleTestResponse>(`/alert-rules/${id}/test`, {
        method: 'POST',
        body: JSON.stringify(data || {}),
      });
    },
  },

  /**
   * Webhooks API namespace (Story 5.3)
   */
  webhooks: {
    /**
     * Test a webhook URL
     * @param data Test request with URL, optional headers and payload
     * @returns Test result with status code and response details
     */
    test: async (data: IWebhookTestRequest): Promise<IWebhookTestResponse> => {
      return apiFetch<IWebhookTestResponse>('/webhooks/test', {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },

    /**
     * Get webhook logs with filtering
     * @param filters Optional filters
     * @returns Paginated list of webhook logs
     */
    getLogs: async (filters?: IWebhookLogsFilter): Promise<IWebhookLogsResponse> => {
      const params = new URLSearchParams();
      if (filters?.rule_id) params.append('rule_id', filters.rule_id);
      if (filters?.success !== undefined) params.append('success', String(filters.success));
      if (filters?.start_date) params.append('start_date', filters.start_date);
      if (filters?.end_date) params.append('end_date', filters.end_date);
      if (filters?.limit) params.append('limit', String(filters.limit));
      if (filters?.offset) params.append('offset', String(filters.offset));

      const queryString = params.toString();
      return apiFetch<IWebhookLogsResponse>(`/webhooks/logs${queryString ? `?${queryString}` : ''}`);
    },

    /**
     * Export webhook logs as CSV
     * @param filters Optional filters
     * @returns CSV file blob
     */
    exportLogs: async (filters?: IWebhookLogsFilter): Promise<Blob> => {
      const params = new URLSearchParams();
      if (filters?.rule_id) params.append('rule_id', filters.rule_id);
      if (filters?.success !== undefined) params.append('success', String(filters.success));
      if (filters?.start_date) params.append('start_date', filters.start_date);
      if (filters?.end_date) params.append('end_date', filters.end_date);

      const queryString = params.toString();
      const response = await fetch(`${API_BASE_URL}/webhooks/logs/export${queryString ? `?${queryString}` : ''}`, {
        method: 'GET',
        headers: {
          'Accept': 'text/csv',
        },
      });

      if (!response.ok) {
        throw new ApiError(`Failed to export logs: ${response.statusText}`, response.status);
      }

      return response.blob();
    },
  },

  /**
   * Notifications API namespace (Story 5.4)
   */
  notifications: {
    /**
     * Get notifications with optional filtering
     * @param filters Optional filters (read status, pagination)
     * @returns Paginated list of notifications with unread count
     */
    list: async (filters?: {
      read?: boolean;
      limit?: number;
      offset?: number;
    }): Promise<INotificationListResponse> => {
      const params = new URLSearchParams();
      if (filters?.read !== undefined) params.append('read', String(filters.read));
      if (filters?.limit) params.append('limit', String(filters.limit));
      if (filters?.offset) params.append('offset', String(filters.offset));

      const queryString = params.toString();
      return apiFetch<INotificationListResponse>(
        `/notifications${queryString ? `?${queryString}` : ''}`
      );
    },

    /**
     * Mark a single notification as read
     * @param id Notification UUID
     * @returns Updated notification
     */
    markAsRead: async (id: string): Promise<INotification> => {
      return apiFetch<INotification>(`/notifications/${id}/read`, {
        method: 'PATCH',
      });
    },

    /**
     * Mark all notifications as read
     * @returns Success status and count of updated notifications
     */
    markAllAsRead: async (): Promise<IMarkReadResponse> => {
      return apiFetch<IMarkReadResponse>('/notifications/mark-all-read', {
        method: 'PATCH',
      });
    },

    /**
     * Delete a single notification
     * @param id Notification UUID
     * @returns Deletion confirmation
     */
    delete: async (id: string): Promise<IDeleteNotificationResponse> => {
      return apiFetch<IDeleteNotificationResponse>(`/notifications/${id}`, {
        method: 'DELETE',
      });
    },

    /**
     * Delete notifications in bulk
     * @param readOnly If true, only delete read notifications
     * @returns Deletion confirmation with count
     */
    deleteAll: async (readOnly: boolean = false): Promise<IBulkDeleteResponse> => {
      const params = new URLSearchParams();
      if (readOnly) params.append('read_only', 'true');
      const queryString = params.toString();
      return apiFetch<IBulkDeleteResponse>(
        `/notifications${queryString ? `?${queryString}` : ''}`,
        { method: 'DELETE' }
      );
    },
  },

  /**
   * Monitoring API client (Story 6.2)
   */
  monitoring: {
    /**
     * Get system health status
     * @returns Health check response
     */
    getHealth: async (): Promise<SystemHealth> => {
      const url = `${API_BASE_URL}/health`;
      const response = await fetch(url);
      if (!response.ok) {
        throw new ApiError('Failed to get health status', response.status);
      }
      return response.json();
    },

    /**
     * Get log entries with filtering
     * @param params Query parameters for filtering logs
     * @returns Paginated log entries
     */
    getLogs: async (params?: LogsQueryParams): Promise<LogsResponse> => {
      const queryParams = new URLSearchParams();
      if (params?.level) queryParams.append('level', params.level);
      if (params?.module) queryParams.append('module', params.module);
      if (params?.search) queryParams.append('search', params.search);
      if (params?.start_date) queryParams.append('start_date', params.start_date);
      if (params?.end_date) queryParams.append('end_date', params.end_date);
      if (params?.limit) queryParams.append('limit', String(params.limit));
      if (params?.offset) queryParams.append('offset', String(params.offset));

      const queryString = queryParams.toString();
      return apiFetch<LogsResponse>(`/logs${queryString ? `?${queryString}` : ''}`);
    },

    /**
     * Get available log files
     * @returns List of log files
     */
    getLogFiles: async (): Promise<LogFilesResponse> => {
      return apiFetch<LogFilesResponse>('/logs/files');
    },

    /**
     * Download log file
     * @param date Optional date string (YYYY-MM-DD)
     * @param logType Log type ('app' or 'error')
     * @returns Blob for download
     */
    downloadLogs: async (date?: string, logType: string = 'app'): Promise<Blob> => {
      const params = new URLSearchParams();
      if (date) params.append('date', date);
      params.append('log_type', logType);
      const queryString = params.toString();

      const url = `${API_BASE_URL}${API_V1_PREFIX}/logs/download${queryString ? `?${queryString}` : ''}`;
      const response = await fetch(url);
      if (!response.ok) {
        throw new ApiError('Failed to download logs', response.status);
      }
      return response.blob();
    },

    /**
     * Get Prometheus metrics
     * @returns Raw metrics text
     */
    getMetrics: async (): Promise<string> => {
      const url = `${API_BASE_URL}/metrics`;
      const response = await fetch(url);
      if (!response.ok) {
        throw new ApiError('Failed to get metrics', response.status);
      }
      return response.text();
    },
  },

  /**
   * Authentication API (Story 6.3)
   */
  auth: {
    /**
     * Login with username and password
     * @param credentials Login credentials
     * @returns Login response with user info
     */
    login: async (credentials: ILoginRequest): Promise<ILoginResponse> => {
      const url = `${API_BASE_URL}${API_V1_PREFIX}/auth/login`;
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials),
        credentials: 'include', // Include cookies
      });

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const errorMessage = data?.detail || `HTTP ${response.status}: ${response.statusText}`;
        throw new ApiError(errorMessage, response.status, data);
      }

      return data as ILoginResponse;
    },

    /**
     * Logout current user
     * @returns Message response
     */
    logout: async (): Promise<IMessageResponse> => {
      const url = `${API_BASE_URL}${API_V1_PREFIX}/auth/logout`;
      const response = await fetch(url, {
        method: 'POST',
        credentials: 'include',
      });

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const errorMessage = data?.detail || `HTTP ${response.status}: ${response.statusText}`;
        throw new ApiError(errorMessage, response.status, data);
      }

      return data as IMessageResponse;
    },

    /**
     * Get current user info
     * @returns Current user
     */
    getCurrentUser: async (): Promise<IUser> => {
      const url = `${API_BASE_URL}${API_V1_PREFIX}/auth/me`;
      const headers: HeadersInit = {};
      const token = getAuthToken();
      if (token) {
        (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(url, {
        credentials: 'include',
        headers,
      });

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const errorMessage = data?.detail || `HTTP ${response.status}: ${response.statusText}`;
        throw new ApiError(errorMessage, response.status, data);
      }

      return data as IUser;
    },

    /**
     * Change password for current user
     * @param passwordData Current and new password
     * @returns Message response
     */
    changePassword: async (passwordData: IChangePasswordRequest): Promise<IMessageResponse> => {
      const url = `${API_BASE_URL}${API_V1_PREFIX}/auth/change-password`;
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      const token = getAuthToken();
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(passwordData),
        credentials: 'include',
      });

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const errorMessage = data?.detail || `HTTP ${response.status}: ${response.statusText}`;
        throw new ApiError(errorMessage, response.status, data);
      }

      return data as IMessageResponse;
    },

    /**
     * Check if initial setup is complete
     * @returns Setup status
     */
    getSetupStatus: async (): Promise<ISetupStatusResponse> => {
      const url = `${API_BASE_URL}${API_V1_PREFIX}/auth/setup-status`;
      const response = await fetch(url);

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const errorMessage = data?.detail || `HTTP ${response.status}: ${response.statusText}`;
        throw new ApiError(errorMessage, response.status, data);
      }

      return data as ISetupStatusResponse;
    },
  },

  /**
   * Backup and Restore API (Story 6.4, FF-007)
   */
  backup: {
    /**
     * Create a system backup with optional selective components (FF-007)
     * @param options Optional backup options for selective backup
     * @returns Backup result with download URL
     */
    create: async (options?: IBackupOptions): Promise<IBackupResponse> => {
      const url = `${API_BASE_URL}${API_V1_PREFIX}/system/backup`;
      const headers: HeadersInit = {
        'Content-Type': 'application/json',
      };
      const token = getAuthToken();
      if (token) {
        (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(url, {
        method: 'POST',
        headers,
        credentials: 'include',
        body: options ? JSON.stringify(options) : undefined,
      });

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const errorMessage = data?.detail || `HTTP ${response.status}: ${response.statusText}`;
        throw new ApiError(errorMessage, response.status, data);
      }

      return data as IBackupResponse;
    },

    /**
     * Download a backup file
     * @param timestamp Backup timestamp
     * @returns Blob containing the ZIP file
     */
    download: async (timestamp: string): Promise<Blob> => {
      const url = `${API_BASE_URL}${API_V1_PREFIX}/system/backup/${timestamp}/download`;
      const response = await fetch(url, {
        credentials: 'include',
      });

      if (!response.ok) {
        throw new ApiError(`Failed to download backup: ${response.statusText}`, response.status);
      }

      return response.blob();
    },

    /**
     * List all available backups
     * @returns List of backups with metadata
     */
    list: async (): Promise<IBackupListResponse> => {
      const url = `${API_BASE_URL}${API_V1_PREFIX}/system/backup/list`;
      const response = await fetch(url, {
        credentials: 'include',
      });

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const errorMessage = data?.detail || `HTTP ${response.status}: ${response.statusText}`;
        throw new ApiError(errorMessage, response.status, data);
      }

      return data as IBackupListResponse;
    },

    /**
     * Validate a backup file before restore
     * @param file ZIP file to validate
     * @returns Validation result
     */
    validate: async (file: File): Promise<IValidationResponse> => {
      const url = `${API_BASE_URL}${API_V1_PREFIX}/system/backup/validate`;
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(url, {
        method: 'POST',
        body: formData,
        credentials: 'include',
      });

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const errorMessage = data?.detail || `HTTP ${response.status}: ${response.statusText}`;
        throw new ApiError(errorMessage, response.status, data);
      }

      return data as IValidationResponse;
    },

    /**
     * Restore from a backup file with optional selective components (FF-007)
     * @param file ZIP file to restore from
     * @param options Optional restore options for selective restore
     * @returns Restore result
     */
    restore: async (file: File, options?: IRestoreOptions): Promise<IRestoreResponse> => {
      const url = `${API_BASE_URL}${API_V1_PREFIX}/system/restore`;
      const formData = new FormData();
      formData.append('file', file);

      // FF-007: Add selective restore options as form fields
      if (options) {
        formData.append('restore_database', String(options.restore_database));
        formData.append('restore_thumbnails', String(options.restore_thumbnails));
        formData.append('restore_settings', String(options.restore_settings));
      }

      const headers: HeadersInit = {};
      const token = getAuthToken();
      if (token) {
        (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: formData,
        credentials: 'include',
      });

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const errorMessage = data?.detail || `HTTP ${response.status}: ${response.statusText}`;
        throw new ApiError(errorMessage, response.status, data);
      }

      return data as IRestoreResponse;
    },

    /**
     * Delete a backup
     * @param timestamp Backup timestamp
     */
    delete: async (timestamp: string): Promise<void> => {
      const url = `${API_BASE_URL}${API_V1_PREFIX}/system/backup/${timestamp}`;
      const response = await fetch(url, {
        method: 'DELETE',
        credentials: 'include',
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        const errorMessage = data?.detail || `HTTP ${response.status}: ${response.statusText}`;
        throw new ApiError(errorMessage, response.status, data);
      }
    },
  },

  // ============================================================================
  // UniFi Protect Controllers (Story P2-1.3)
  // ============================================================================
  protect: {
    /**
     * Test connection to a UniFi Protect controller
     * Does NOT save credentials - test only
     * @param data Connection parameters
     */
    testConnection: async (data: {
      host: string;
      port?: number;
      username: string;
      password: string;
      verify_ssl?: boolean;
    }): Promise<{
      data: {
        success: boolean;
        message: string;
        firmware_version?: string;
        camera_count?: number;
      };
      meta: { request_id: string; timestamp: string };
    }> => {
      return apiFetch(`/protect/controllers/test`, {
        method: 'POST',
        body: JSON.stringify({
          host: data.host,
          port: data.port ?? 443,
          username: data.username,
          password: data.password,
          verify_ssl: data.verify_ssl ?? false,
        }),
      });
    },

    /**
     * Create a new UniFi Protect controller
     * @param data Controller configuration
     */
    createController: async (data: {
      name: string;
      host: string;
      port?: number;
      username: string;
      password: string;
      verify_ssl?: boolean;
    }): Promise<{
      data: {
        id: string;
        name: string;
        host: string;
        port: number;
        username: string;
        verify_ssl: boolean;
        is_connected: boolean;
        last_connected_at: string | null;
        last_error: string | null;
        created_at: string;
        updated_at: string;
      };
      meta: { request_id: string; timestamp: string };
    }> => {
      return apiFetch(`/protect/controllers`, {
        method: 'POST',
        body: JSON.stringify({
          name: data.name,
          host: data.host,
          port: data.port ?? 443,
          username: data.username,
          password: data.password,
          verify_ssl: data.verify_ssl ?? false,
        }),
      });
    },

    /**
     * List all UniFi Protect controllers
     */
    listControllers: async (): Promise<{
      data: Array<{
        id: string;
        name: string;
        host: string;
        port: number;
        username: string;
        verify_ssl: boolean;
        is_connected: boolean;
        last_connected_at: string | null;
        last_error: string | null;
        created_at: string;
        updated_at: string;
      }>;
      meta: { request_id: string; timestamp: string; count?: number };
    }> => {
      return apiFetch(`/protect/controllers`);
    },

    /**
     * Get a single UniFi Protect controller by ID
     * @param id Controller UUID
     */
    getController: async (id: string): Promise<{
      data: {
        id: string;
        name: string;
        host: string;
        port: number;
        username: string;
        verify_ssl: boolean;
        is_connected: boolean;
        last_connected_at: string | null;
        last_error: string | null;
        created_at: string;
        updated_at: string;
      };
      meta: { request_id: string; timestamp: string };
    }> => {
      return apiFetch(`/protect/controllers/${id}`);
    },

    /**
     * Test connection to an existing controller using stored credentials
     * @param id Controller UUID
     */
    testExistingController: async (id: string): Promise<{
      data: {
        success: boolean;
        message: string;
        firmware_version?: string;
        camera_count?: number;
      };
      meta: { request_id: string; timestamp: string };
    }> => {
      return apiFetch(`/protect/controllers/${id}/test`, {
        method: 'POST',
      });
    },

    /**
     * Update a UniFi Protect controller (Story P2-1.5)
     * Supports partial updates - only provided fields are modified
     * @param id Controller UUID
     * @param data Partial controller data to update
     */
    updateController: async (id: string, data: {
      name?: string;
      host?: string;
      port?: number;
      username?: string;
      password?: string;
      verify_ssl?: boolean;
    }): Promise<{
      data: {
        id: string;
        name: string;
        host: string;
        port: number;
        username: string;
        verify_ssl: boolean;
        is_connected: boolean;
        last_connected_at: string | null;
        last_error: string | null;
        created_at: string;
        updated_at: string;
      };
      meta: { request_id: string; timestamp: string };
    }> => {
      return apiFetch(`/protect/controllers/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      });
    },

    /**
     * Delete a UniFi Protect controller (Story P2-1.5)
     * Disconnects WebSocket, disassociates cameras, preserves events
     * @param id Controller UUID
     */
    deleteController: async (id: string): Promise<{
      data: { deleted: boolean };
      meta: { request_id: string; timestamp: string };
    }> => {
      return apiFetch(`/protect/controllers/${id}`, {
        method: 'DELETE',
      });
    },

    /**
     * Discover cameras from a connected Protect controller (Story P2-2.1)
     * Results are cached for 60 seconds
     * @param controllerId Controller UUID
     * @param forceRefresh If true, bypass cache and fetch fresh data
     */
    discoverCameras: async (controllerId: string, forceRefresh: boolean = false): Promise<{
      data: ProtectDiscoveredCamera[];
      meta: {
        request_id: string;
        timestamp: string;
        count: number;
        controller_id: string;
        cached: boolean;
        cached_at: string | null;
        warning: string | null;
      };
    }> => {
      const params = forceRefresh ? '?force_refresh=true' : '';
      return apiFetch(`/protect/controllers/${controllerId}/cameras${params}`);
    },

    /**
     * Enable a discovered camera for AI analysis (Story P2-2.2)
     * Creates or updates camera record in database with source_type='protect'
     * @param controllerId Controller UUID
     * @param cameraId Protect camera ID
     * @param options Optional name override and smart detection types
     */
    enableCamera: async (
      controllerId: string,
      cameraId: string,
      options?: { name?: string; smart_detection_types?: string[] }
    ): Promise<{
      data: ProtectCameraEnableData;
      meta: { request_id: string; timestamp: string };
    }> => {
      return apiFetch(`/protect/controllers/${controllerId}/cameras/${cameraId}/enable`, {
        method: 'POST',
        body: options ? JSON.stringify(options) : undefined,
      });
    },

    /**
     * Disable a camera from AI analysis (Story P2-2.2)
     * Keeps camera record but marks as disabled for settings persistence
     * @param controllerId Controller UUID
     * @param cameraId Protect camera ID
     */
    disableCamera: async (
      controllerId: string,
      cameraId: string
    ): Promise<{
      data: ProtectCameraDisableData;
      meta: { request_id: string; timestamp: string };
    }> => {
      return apiFetch(`/protect/controllers/${controllerId}/cameras/${cameraId}/disable`, {
        method: 'POST',
      });
    },

    /**
     * Update camera event type filters (Story P2-2.3)
     * Updates smart_detection_types for an enabled camera
     * @param controllerId Controller UUID
     * @param cameraId Protect camera ID
     * @param filters The filter configuration
     */
    updateCameraFilters: async (
      controllerId: string,
      cameraId: string,
      filters: { smart_detection_types: string[] }
    ): Promise<{
      data: ProtectCameraFiltersData;
      meta: { request_id: string; timestamp: string };
    }> => {
      return apiFetch(`/protect/controllers/${controllerId}/cameras/${cameraId}/filters`, {
        method: 'PUT',
        body: JSON.stringify(filters),
      });
    },
  },

  // ============================================================================
  // Push Notifications (Story P4-1.2)
  // ============================================================================
  push: {
    /**
     * Get VAPID public key for push subscription
     * The frontend uses this key as applicationServerKey when calling pushManager.subscribe()
     * @returns VAPID public key in URL-safe base64 format
     */
    getVapidPublicKey: async (): Promise<{ public_key: string }> => {
      return apiFetch<{ public_key: string }>('/push/vapid-public-key');
    },

    /**
     * Register a push subscription
     * Stores the browser's push subscription for receiving notifications
     * If the endpoint already exists, the subscription is updated (upsert)
     * @param subscription Browser PushSubscription data
     * @returns Created/updated subscription with ID
     */
    subscribe: async (subscription: {
      endpoint: string;
      keys: { p256dh: string; auth: string };
      user_agent?: string;
    }): Promise<{ id: string; endpoint: string; created_at: string }> => {
      return apiFetch<{ id: string; endpoint: string; created_at: string }>('/push/subscribe', {
        method: 'POST',
        body: JSON.stringify(subscription),
      });
    },

    /**
     * Unsubscribe from push notifications
     * Removes the push subscription from the database
     * @param endpoint Push service endpoint URL to unsubscribe
     */
    unsubscribe: async (endpoint: string): Promise<void> => {
      const url = `${API_BASE_URL}${API_V1_PREFIX}/push/subscribe`;
      const headers: HeadersInit = { 'Content-Type': 'application/json' };
      const token = getAuthToken();
      if (token) {
        (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(url, {
        method: 'DELETE',
        headers,
        credentials: 'include',
        body: JSON.stringify({ endpoint }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        const errorMessage = data?.detail || `HTTP ${response.status}: ${response.statusText}`;
        throw new ApiError(errorMessage, response.status, data);
      }
    },

    /**
     * List all push subscriptions (admin endpoint)
     * Returns all registered push subscriptions for debugging
     * @returns List of subscriptions with metadata
     */
    listSubscriptions: async (): Promise<{
      subscriptions: Array<{
        id: string;
        user_id: string | null;
        endpoint: string;
        user_agent: string | null;
        created_at: string | null;
        last_used_at: string | null;
      }>;
      total: number;
    }> => {
      return apiFetch('/push/subscriptions');
    },

    /**
     * Send a test push notification
     * Sends a test notification to all subscribed devices
     * @returns Test result with delivery status
     */
    sendTest: async (): Promise<{
      success: boolean;
      message: string;
      results?: Array<{
        subscription_id: string;
        success: boolean;
        error?: string;
      }>;
    }> => {
      return apiFetch('/push/test', {
        method: 'POST',
      });
    },

    /**
     * Get notification preferences for a subscription (Story P4-1.4)
     * Returns preferences identified by the subscription endpoint
     * Creates default preferences if none exist
     * @param endpoint Push subscription endpoint URL
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
     * @param preferences Notification preferences to update
     * @returns Updated preferences
     */
    updatePreferences: async (preferences: {
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
        body: JSON.stringify(preferences),
      });
    },
  },

  // ============================================================================
  // MQTT / Home Assistant Integration (Story P4-2.4)
  // ============================================================================
  mqtt: {
    /**
     * Get current MQTT configuration
     * @returns MQTT configuration with has_password boolean (password omitted)
     */
    getConfig: async (): Promise<MQTTConfigResponse> => {
      return apiFetch<MQTTConfigResponse>('/integrations/mqtt/config');
    },

    /**
     * Update MQTT configuration
     * Triggers reconnect if enabled
     * @param config Configuration to update
     * @returns Updated configuration
     */
    updateConfig: async (config: MQTTConfigUpdate): Promise<MQTTConfigResponse> => {
      return apiFetch<MQTTConfigResponse>('/integrations/mqtt/config', {
        method: 'PUT',
        body: JSON.stringify(config),
      });
    },

    /**
     * Get MQTT connection status
     * @returns Connection status with statistics
     */
    getStatus: async (): Promise<MQTTStatusResponse> => {
      return apiFetch<MQTTStatusResponse>('/integrations/mqtt/status');
    },

    /**
     * Test MQTT connection without persisting
     * @param testRequest Connection parameters to test
     * @returns Test result with success/failure message
     */
    testConnection: async (testRequest: MQTTTestRequest): Promise<MQTTTestResponse> => {
      return apiFetch<MQTTTestResponse>('/integrations/mqtt/test', {
        method: 'POST',
        body: JSON.stringify(testRequest),
      });
    },

    /**
     * Publish Home Assistant discovery for all cameras
     * Requires MQTT to be connected and discovery enabled
     * @returns Number of cameras published
     */
    publishDiscovery: async (): Promise<MQTTPublishDiscoveryResponse> => {
      return apiFetch<MQTTPublishDiscoveryResponse>('/integrations/mqtt/publish-discovery', {
        method: 'POST',
      });
    },
  },

  // ============================================================================
  // HomeKit Integration (Story P4-6.1, P5-1.8)
  // ============================================================================
  homekit: {
    /**
     * Get current HomeKit status
     * @returns HomeKit status including enabled, running, paired state, and setup code
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
      return apiFetch('/integrations/homekit/status');
    },

    /**
     * Enable or disable HomeKit integration
     * @param enabled Whether to enable HomeKit
     * @returns Updated HomeKit status
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
      return apiFetch('/integrations/homekit/enable', {
        method: 'PUT',
        body: JSON.stringify({ enabled }),
      });
    },

    /**
     * Reset HomeKit pairing
     * Removes existing pairing state, requiring re-pairing with Home app
     * @returns Reset result with new setup code
     */
    resetPairing: async (): Promise<{
      success: boolean;
      message: string;
      new_setup_code: string | null;
    }> => {
      return apiFetch('/integrations/homekit/reset', {
        method: 'POST',
      });
    },

    /**
     * Get list of paired devices (Story P5-1.8)
     * @returns List of paired clients with their info
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
     * Remove a specific pairing (Story P5-1.8)
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
     * Get a single entity with recent events
     * @param entityId UUID of the entity
     * @param eventLimit Maximum number of recent events to include (default 10)
     * @returns Entity detail with recent events
     * @throws ApiError with 404 if not found
     */
    getById: async (entityId: string, eventLimit?: number): Promise<{
      id: string;
      entity_type: string;
      name: string | null;
      first_seen_at: string;
      last_seen_at: string;
      occurrence_count: number;
      created_at: string;
      updated_at: string;
      recent_events: Array<{
        id: string;
        timestamp: string;
        description: string;
        thumbnail_url: string | null;
        camera_id: string;
        similarity_score: number;
      }>;
    }> => {
      const params = eventLimit ? `?event_limit=${eventLimit}` : '';
      return apiFetch(`/context/entities/${entityId}${params}`);
    },

    /**
     * Update an entity's name
     * @param entityId UUID of the entity
     * @param data Update data with name
     * @returns Updated entity
     * @throws ApiError with 404 if not found
     */
    update: async (entityId: string, data: { name: string | null }): Promise<{
      id: string;
      entity_type: string;
      name: string | null;
      first_seen_at: string;
      last_seen_at: string;
      occurrence_count: number;
    }> => {
      return apiFetch(`/context/entities/${entityId}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      });
    },

    /**
     * Delete an entity
     * Unlinks all associated events (events are not deleted)
     * @param entityId UUID of the entity
     * @throws ApiError with 404 if not found
     */
    delete: async (entityId: string): Promise<void> => {
      const url = `${API_BASE_URL}${API_V1_PREFIX}/context/entities/${entityId}`;
      const headers: HeadersInit = { 'Content-Type': 'application/json' };
      const token = getAuthToken();
      if (token) {
        (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(url, {
        method: 'DELETE',
        headers,
        credentials: 'include',
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        const errorMessage = data?.detail || `HTTP ${response.status}: ${response.statusText}`;
        throw new ApiError(errorMessage, response.status, data);
      }
      // 204 No Content - no body to parse
    },
  },

  // ============================================================================
  // Activity Summaries (Story P4-4.4, P4-4.5)
  // ============================================================================
  summaries: {
    /**
     * Get recent summaries for dashboard display
     * Returns today's and yesterday's activity summaries if they exist
     * @returns Recent summaries with event statistics
     */
    recent: async (): Promise<RecentSummariesResponse> => {
      return apiFetch<RecentSummariesResponse>('/summaries/recent');
    },

    /**
     * Generate an on-demand summary for a time period (Story P4-4.5)
     *
     * Accepts EITHER:
     * - hours_back: Shorthand for "last N hours" (e.g., hours_back: 3 for last 3 hours)
     * - OR start_time + end_time: Explicit time range
     *
     * @param params Generation parameters
     * @returns Generated summary with stats
     */
    generate: async (params: SummaryGenerateRequest): Promise<SummaryGenerateResponse> => {
      return apiFetch<SummaryGenerateResponse>('/summaries/generate', {
        method: 'POST',
        body: JSON.stringify(params),
      });
    },

    /**
     * List all summaries with pagination
     * @param limit Maximum number to return (default 20)
     * @param offset Pagination offset (default 0)
     * @returns List of summaries
     */
    list: async (limit = 20, offset = 0): Promise<SummaryListResponse> => {
      const params = new URLSearchParams({
        limit: String(limit),
        offset: String(offset),
      });
      return apiFetch<SummaryListResponse>(`/summaries?${params}`);
    },
  },
};

// Story P2-2.1: Camera Discovery Types

/** Discovered camera from Protect controller */
export interface ProtectDiscoveredCamera {
  protect_camera_id: string;
  name: string;
  type: 'camera' | 'doorbell';
  model: string;
  is_online: boolean;
  is_doorbell: boolean;
  is_enabled_for_ai: boolean;
  smart_detection_capabilities: string[];
  /** Configured filter types for enabled cameras (Story P2-2.3) */
  smart_detection_types?: string[] | null;
  /** Whether this camera was newly discovered (not in database) (Story P2-2.4 AC11) */
  is_new?: boolean;
  /** Database camera ID (only set when camera is enabled for AI) (Story P3-3.3) */
  camera_id?: string | null;
  /** AI analysis mode for this camera (Story P3-3.3) */
  analysis_mode?: 'single_frame' | 'multi_frame' | 'video_native' | null;
}

// Story P2-2.2: Camera Enable/Disable Types

/** Response data when camera is enabled for AI */
export interface ProtectCameraEnableData {
  camera_id: string;
  protect_camera_id: string;
  name: string;
  is_enabled_for_ai: boolean;
  smart_detection_types: string[];
}

/** Response data when camera is disabled */
export interface ProtectCameraDisableData {
  protect_camera_id: string;
  is_enabled_for_ai: boolean;
}

// Story P2-2.3: Camera Filters Types

/** Response data when camera filters are updated */
export interface ProtectCameraFiltersData {
  protect_camera_id: string;
  name: string;
  smart_detection_types: string[];
  is_enabled_for_ai: boolean;
}

// Story P4-1.2: Push Notification Types (re-exported from types/push.ts)
export type {
  IVapidPublicKeyResponse,
  IPushSubscribeRequest,
  IPushSubscriptionResponse,
  IPushUnsubscribeRequest,
  IPushSubscriptionsListResponse,
  IPushTestResponse,
} from '@/types/push';

// Story P4-3.6: Entity Types (re-exported from types/entity.ts)
export type {
  IEntity,
  IEntityDetail,
  IEntityListResponse,
  IEntityQueryParams,
  IEntityUpdateRequest,
  EntityType,
} from '@/types/entity';

// Story P4-4.4 & P4-4.5: Activity Summary Types

/** Summary item from recent summaries endpoint */
export interface RecentSummaryItem {
  id: string;
  date: string;
  summary_text: string;
  event_count: number;
  camera_count: number;
  alert_count: number;
  doorbell_count: number;
  person_count: number;
  vehicle_count: number;
  generated_at: string;
}

/** Response from GET /api/v1/summaries/recent */
export interface RecentSummariesResponse {
  summaries: RecentSummaryItem[];
}

/** Statistical breakdown of events in summary (Story P4-4.5) */
export interface SummaryStats {
  total_events: number;
  by_type: Record<string, number>;
  by_camera: Record<string, number>;
  alerts_triggered: number;
  doorbell_rings: number;
}

/**
 * Request for on-demand summary generation (Story P4-4.5)
 *
 * Either hours_back OR (start_time AND end_time) must be provided, not both.
 */
export interface SummaryGenerateRequest {
  /** Generate summary for last N hours (1-168). Mutually exclusive with start_time/end_time. */
  hours_back?: number;
  /** Start of time period (ISO 8601). Required if hours_back not provided. */
  start_time?: string;
  /** End of time period (ISO 8601). Required if hours_back not provided. */
  end_time?: string;
  /** List of camera UUIDs to include (null = all cameras) */
  camera_ids?: string[] | null;
}

/** Response from POST /api/v1/summaries/generate (Story P4-4.5) */
export interface SummaryGenerateResponse {
  id: string;
  summary_text: string;
  period_start: string;
  period_end: string;
  event_count: number;
  generated_at: string;
  stats: SummaryStats | null;
  ai_cost: number;
  provider_used: string | null;
  camera_count: number;
  alert_count: number;
  doorbell_count: number;
  person_count: number;
  vehicle_count: number;
}

/** Response from GET /api/v1/summaries (Story P4-4.5) */
export interface SummaryListResponse {
  summaries: SummaryGenerateResponse[];
  total: number;
}
