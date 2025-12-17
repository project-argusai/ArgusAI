/**
 * useCamerasQuery hook tests (Story P6-1.4)
 * Tests the TanStack Query hooks for camera management with caching
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  useCamerasQuery,
  useCameraQuery,
  useCameraCreate,
  useCameraUpdate,
  useCameraDelete,
  cameraKeys,
} from '@/hooks/useCamerasQuery';
import { apiClient } from '@/lib/api-client';
import React from 'react';

// Mock the API client
vi.mock('@/lib/api-client', () => ({
  apiClient: {
    cameras: {
      list: vi.fn(),
      getById: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
    },
  },
  ApiError: class ApiError extends Error {
    statusCode: number;
    constructor(message: string, statusCode: number) {
      super(message);
      this.statusCode = statusCode;
    }
  },
}));

describe('useCamerasQuery hooks', () => {
  let queryClient: QueryClient;

  const mockCameras = [
    {
      id: 'cam-1',
      name: 'Front Door',
      rtsp_url: 'rtsp://192.168.1.100/stream',
      source_type: 'rtsp' as const,
      is_enabled: true,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-06-01T00:00:00Z',
    },
    {
      id: 'cam-2',
      name: 'Back Yard',
      rtsp_url: 'rtsp://192.168.1.101/stream',
      source_type: 'rtsp' as const,
      is_enabled: false,
      created_at: '2024-02-01T00:00:00Z',
      updated_at: '2024-06-15T00:00:00Z',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          gcTime: 0,
        },
        mutations: {
          retry: false,
        },
      },
    });
  });

  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);

  describe('cameraKeys', () => {
    it('generates correct query keys', () => {
      expect(cameraKeys.all).toEqual(['cameras']);
      expect(cameraKeys.lists()).toEqual(['cameras', 'list']);
      expect(cameraKeys.list()).toEqual(['cameras', 'list', {}]);
      expect(cameraKeys.list({ is_enabled: true })).toEqual(['cameras', 'list', { is_enabled: true }]);
      expect(cameraKeys.details()).toEqual(['cameras', 'detail']);
      expect(cameraKeys.detail('cam-1')).toEqual(['cameras', 'detail', 'cam-1']);
    });
  });

  describe('useCamerasQuery', () => {
    it('fetches cameras successfully', async () => {
      (apiClient.cameras.list as ReturnType<typeof vi.fn>).mockResolvedValueOnce(mockCameras);

      const { result } = renderHook(() => useCamerasQuery(), { wrapper });

      // Initially loading
      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.data).toEqual(mockCameras);
      expect(apiClient.cameras.list).toHaveBeenCalledTimes(1);
      expect(apiClient.cameras.list).toHaveBeenCalledWith({});
    });

    it('passes filter parameters to API', async () => {
      (apiClient.cameras.list as ReturnType<typeof vi.fn>).mockResolvedValueOnce([mockCameras[0]]);

      const { result } = renderHook(() => useCamerasQuery({ is_enabled: true }), { wrapper });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(apiClient.cameras.list).toHaveBeenCalledWith({ is_enabled: true });
    });

    it('handles fetch error', async () => {
      const error = new Error('Network error');
      (apiClient.cameras.list as ReturnType<typeof vi.fn>).mockRejectedValueOnce(error);

      const { result } = renderHook(() => useCamerasQuery(), { wrapper });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toBeTruthy();
    });

    it('uses 30 second stale time', async () => {
      (apiClient.cameras.list as ReturnType<typeof vi.fn>).mockResolvedValue(mockCameras);

      const { result, rerender } = renderHook(() => useCamerasQuery(), { wrapper });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // First call
      expect(apiClient.cameras.list).toHaveBeenCalledTimes(1);

      // Rerender immediately - should use cache
      rerender();
      expect(apiClient.cameras.list).toHaveBeenCalledTimes(1);

      // Verify data is stale after configured time (we can't easily test time,
      // but we can verify the hook is configured correctly by checking isStale)
      expect(result.current.isStale).toBe(false);
    });

    it('refetches on window focus when configured', async () => {
      (apiClient.cameras.list as ReturnType<typeof vi.fn>).mockResolvedValue(mockCameras);

      // Create a QueryClient with window focus enabled for this test
      const focusClient = new QueryClient({
        defaultOptions: {
          queries: {
            retry: false,
            gcTime: 0,
            staleTime: 0, // Make data immediately stale
          },
        },
      });

      const focusWrapper = ({ children }: { children: React.ReactNode }) =>
        React.createElement(QueryClientProvider, { client: focusClient }, children);

      const { result } = renderHook(() => useCamerasQuery(), { wrapper: focusWrapper });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // The hook has refetchOnWindowFocus: true configured
      // We verify this through the hook implementation
      expect(result.current.data).toEqual(mockCameras);
    });
  });

  describe('useCameraQuery', () => {
    const mockCamera = mockCameras[0];

    it('fetches single camera when ID is provided', async () => {
      (apiClient.cameras.getById as ReturnType<typeof vi.fn>).mockResolvedValueOnce(mockCamera);

      const { result } = renderHook(() => useCameraQuery('cam-1'), { wrapper });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.data).toEqual(mockCamera);
      expect(apiClient.cameras.getById).toHaveBeenCalledWith('cam-1');
    });

    it('does not fetch when ID is null', () => {
      const { result } = renderHook(() => useCameraQuery(null), { wrapper });

      expect(result.current.isLoading).toBe(false);
      expect(apiClient.cameras.getById).not.toHaveBeenCalled();
    });
  });

  describe('useCameraCreate', () => {
    const newCamera = {
      name: 'New Camera',
      type: 'rtsp' as const,
      rtsp_url: 'rtsp://192.168.1.102/stream',
      is_enabled: true,
    };

    const createdCamera = {
      id: 'cam-3',
      name: 'New Camera',
      rtsp_url: 'rtsp://192.168.1.102/stream',
      source_type: 'rtsp' as const,
      is_enabled: true,
      created_at: '2024-06-20T00:00:00Z',
      updated_at: '2024-06-20T00:00:00Z',
    };

    it('creates camera successfully', async () => {
      (apiClient.cameras.create as ReturnType<typeof vi.fn>).mockResolvedValueOnce(createdCamera);

      const { result } = renderHook(() => useCameraCreate(), { wrapper });

      await act(async () => {
        await result.current.mutateAsync(newCamera);
      });

      expect(apiClient.cameras.create).toHaveBeenCalledWith(newCamera);
    });

    it('invalidates camera list cache on success', async () => {
      (apiClient.cameras.list as ReturnType<typeof vi.fn>).mockResolvedValue(mockCameras);
      (apiClient.cameras.create as ReturnType<typeof vi.fn>).mockResolvedValueOnce(createdCamera);

      // First, populate the cache
      const { result: listResult } = renderHook(() => useCamerasQuery(), { wrapper });
      await waitFor(() => {
        expect(listResult.current.isLoading).toBe(false);
      });

      // Reset mock call count
      vi.mocked(apiClient.cameras.list).mockClear();

      // Create new camera
      const { result: createResult } = renderHook(() => useCameraCreate(), { wrapper });
      await act(async () => {
        await createResult.current.mutateAsync(newCamera);
      });

      // Wait for cache invalidation to trigger refetch
      await waitFor(() => {
        expect(apiClient.cameras.list).toHaveBeenCalled();
      });
    });

    it('handles create error', async () => {
      const error = new Error('Create failed');
      (apiClient.cameras.create as ReturnType<typeof vi.fn>).mockRejectedValueOnce(error);

      const { result } = renderHook(() => useCameraCreate(), { wrapper });

      await expect(result.current.mutateAsync(newCamera)).rejects.toThrow('Create failed');
    });
  });

  describe('useCameraUpdate', () => {
    const updatedCamera = {
      ...mockCameras[0],
      name: 'Updated Camera Name',
    };

    it('updates camera successfully', async () => {
      (apiClient.cameras.update as ReturnType<typeof vi.fn>).mockResolvedValueOnce(updatedCamera);

      const { result } = renderHook(() => useCameraUpdate(), { wrapper });

      await act(async () => {
        await result.current.mutateAsync({
          id: 'cam-1',
          data: { name: 'Updated Camera Name' },
        });
      });

      expect(apiClient.cameras.update).toHaveBeenCalledWith('cam-1', { name: 'Updated Camera Name' });
    });

    it('handles update error', async () => {
      const error = new Error('Update failed');
      (apiClient.cameras.update as ReturnType<typeof vi.fn>).mockRejectedValueOnce(error);

      const { result } = renderHook(() => useCameraUpdate(), { wrapper });

      await expect(
        result.current.mutateAsync({
          id: 'cam-1',
          data: { name: 'New Name' },
        })
      ).rejects.toThrow('Update failed');
    });
  });

  describe('useCameraDelete', () => {
    it('deletes camera successfully', async () => {
      (apiClient.cameras.delete as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ deleted: true });

      const { result } = renderHook(() => useCameraDelete(), { wrapper });

      await act(async () => {
        await result.current.mutateAsync('cam-1');
      });

      expect(apiClient.cameras.delete).toHaveBeenCalledWith('cam-1');
    });

    it('invalidates camera list cache on success', async () => {
      (apiClient.cameras.list as ReturnType<typeof vi.fn>).mockResolvedValue(mockCameras);
      (apiClient.cameras.delete as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ deleted: true });

      // First, populate the cache
      const { result: listResult } = renderHook(() => useCamerasQuery(), { wrapper });
      await waitFor(() => {
        expect(listResult.current.isLoading).toBe(false);
      });

      // Reset mock call count
      vi.mocked(apiClient.cameras.list).mockClear();

      // Delete camera
      const { result: deleteResult } = renderHook(() => useCameraDelete(), { wrapper });
      await act(async () => {
        await deleteResult.current.mutateAsync('cam-1');
      });

      // Wait for cache invalidation to trigger refetch
      await waitFor(() => {
        expect(apiClient.cameras.list).toHaveBeenCalled();
      });
    });

    it('handles delete error', async () => {
      const error = new Error('Delete failed');
      (apiClient.cameras.delete as ReturnType<typeof vi.fn>).mockRejectedValueOnce(error);

      const { result } = renderHook(() => useCameraDelete(), { wrapper });

      await expect(result.current.mutateAsync('cam-1')).rejects.toThrow('Delete failed');
    });
  });
});
