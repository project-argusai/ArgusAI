/**
 * API Client for Live Object AI Classifier Backend
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
} from '@/types/event';
import type {
  SystemSettings,
  StorageStats,
  AIKeyTestRequest,
  AIKeyTestResponse,
  DeleteDataResponse,
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
      const response = await fetch(url);
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
   * Backup and Restore API (Story 6.4)
   */
  backup: {
    /**
     * Create a full system backup
     * @returns Backup result with download URL
     */
    create: async (): Promise<IBackupResponse> => {
      const url = `${API_BASE_URL}${API_V1_PREFIX}/system/backup`;
      const response = await fetch(url, {
        method: 'POST',
        credentials: 'include',
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
     * Restore from a backup file
     * @param file ZIP file to restore from
     * @returns Restore result
     */
    restore: async (file: File): Promise<IRestoreResponse> => {
      const url = `${API_BASE_URL}${API_V1_PREFIX}/system/restore`;
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
