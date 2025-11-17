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
};
