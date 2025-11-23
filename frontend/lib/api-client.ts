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
} from '@/types/alert-rule';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_V1_PREFIX = '/api/v1';

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
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
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
     * @param data Model and API key to test
     * @returns Test result with validation status
     */
    testApiKey: async (data: AIKeyTestRequest): Promise<AIKeyTestResponse> => {
      return apiFetch<AIKeyTestResponse>('/ai/test-key', {
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
};
