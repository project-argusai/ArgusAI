/**
 * Custom hooks for camera preview polling and manual analysis
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';

/**
 * Hook to check if page is visible (for pausing polling)
 */
function usePageVisibility() {
  const [isVisible, setIsVisible] = useState(true);

  useEffect(() => {
    const handleVisibilityChange = () => {
      setIsVisible(!document.hidden);
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, []);

  return isVisible;
}

/**
 * Hook for fetching camera preview with auto-refresh polling
 */
export function useCameraPreview(cameraId: string, enabled = true) {
  const isPageVisible = usePageVisibility();

  return useQuery({
    queryKey: ['camera-preview', cameraId],
    queryFn: async () => {
      const response = await apiClient.cameras.preview(cameraId);

      // Convert to data URL if base64 is provided
      if (response.thumbnail_base64) {
        return `data:image/jpeg;base64,${response.thumbnail_base64}`;
      }

      // Return path if provided
      if (response.thumbnail_path) {
        return `/api/v1/thumbnails/${response.thumbnail_path}`;
      }

      return null;
    },
    enabled: enabled && isPageVisible, // Only poll when enabled and page visible
    refetchInterval: 2000, // Poll every 2 seconds
    staleTime: 1000, // Consider data stale after 1 second
    retry: 2, // Retry failed requests twice
  });
}

/**
 * Hook for triggering manual camera analysis
 */
export function useAnalyzeCamera() {
  const queryClient = useQueryClient();
  const router = useRouter();

  return useMutation({
    mutationFn: (cameraId: string) => apiClient.cameras.analyze(cameraId),
    onSuccess: (data, cameraId) => {
      // Invalidate camera preview to show latest frame
      queryClient.invalidateQueries({ queryKey: ['camera-preview', cameraId] });

      // Show success message
      toast.success('Analysis complete - check Events timeline', {
        action: {
          label: 'View Events',
          onClick: () => router.push('/events'),
        },
      });
    },
    onError: (error) => {
      toast.error('Failed to analyze camera frame', {
        description: error instanceof Error ? error.message : 'Unknown error',
      });
    },
  });
}
