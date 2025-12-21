/**
 * Custom hook for fetching a single camera by ID
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import { apiClient, ApiError } from '@/lib/api-client';
import type { ICamera } from '@/types/camera';

interface UseCameraDetailOptions {
  /**
   * Whether to fetch automatically on mount
   */
  autoFetch?: boolean;
}

interface UseCameraDetailReturn {
  /**
   * Camera object (null if not loaded)
   */
  camera: ICamera | null;
  /**
   * Loading state
   */
  loading: boolean;
  /**
   * Error message if fetch failed
   */
  error: string | null;
  /**
   * Refresh camera data
   */
  refresh: () => Promise<void>;
}

/**
 * Hook to fetch and manage single camera details
 * @param id Camera UUID
 * @param options Fetch options (autoFetch)
 * @returns Camera state and refresh function
 */
export function useCameraDetail(
  id: string,
  options: UseCameraDetailOptions = { autoFetch: true }
): UseCameraDetailReturn {
  const [camera, setCamera] = useState<ICamera | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCamera = useCallback(async () => {
    if (!id) {
      setError('Camera ID is required');
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data = await apiClient.cameras.get(id);
      setCamera(data);
    } catch (err) {
      const errorMessage =
        err instanceof ApiError
          ? err.message
          : 'Failed to fetch camera';
      setError(errorMessage);
      setCamera(null);
    } finally {
      setLoading(false);
    }
  }, [id]);

  // Auto-fetch on mount if enabled
  useEffect(() => {
    if (options.autoFetch !== false) {
      fetchCamera();
    }
  }, [options.autoFetch, fetchCamera]);

  return {
    camera,
    loading,
    error,
    refresh: fetchCamera,
  };
}
