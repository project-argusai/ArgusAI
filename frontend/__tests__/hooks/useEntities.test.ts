/**
 * useEntities hook integration tests (Story P4-3.6)
 * Tests the TanStack Query hooks for entity management
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEntities, useEntity, useUpdateEntity, useDeleteEntity } from '@/hooks/useEntities';
import { apiClient } from '@/lib/api-client';
import React from 'react';

// Mock the API client
vi.mock('@/lib/api-client', () => ({
  apiClient: {
    entities: {
      list: vi.fn(),
      getById: vi.fn(),
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

describe('useEntities hook', () => {
  let queryClient: QueryClient;

  const mockEntitiesResponse = {
    entities: [
      {
        id: 'entity-1',
        entity_type: 'person',
        name: 'John',
        first_seen_at: '2024-01-01T00:00:00Z',
        last_seen_at: '2024-06-01T00:00:00Z',
        occurrence_count: 10,
      },
      {
        id: 'entity-2',
        entity_type: 'vehicle',
        name: null,
        first_seen_at: '2024-02-01T00:00:00Z',
        last_seen_at: '2024-06-15T00:00:00Z',
        occurrence_count: 5,
      },
    ],
    total: 2,
  };

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

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  );

  describe('useEntities', () => {
    it('fetches entities successfully', async () => {
      (apiClient.entities.list as ReturnType<typeof vi.fn>).mockResolvedValueOnce(mockEntitiesResponse);

      const { result } = renderHook(() => useEntities(), { wrapper });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.data).toEqual(mockEntitiesResponse);
      expect(apiClient.entities.list).toHaveBeenCalledTimes(1);
    });

    it('passes query parameters to API', async () => {
      (apiClient.entities.list as ReturnType<typeof vi.fn>).mockResolvedValueOnce(mockEntitiesResponse);

      const params = {
        limit: 20,
        offset: 10,
        entity_type: 'person' as const,
        named_only: true,
      };

      const { result } = renderHook(() => useEntities(params), { wrapper });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(apiClient.entities.list).toHaveBeenCalledWith(params);
    });

    it('handles fetch error', async () => {
      const error = new Error('Network error');
      (apiClient.entities.list as ReturnType<typeof vi.fn>).mockRejectedValueOnce(error);

      const { result } = renderHook(() => useEntities(), { wrapper });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toBeTruthy();
    });
  });

  describe('useEntity', () => {
    const mockEntityDetail = {
      id: 'entity-1',
      entity_type: 'person',
      name: 'John',
      first_seen_at: '2024-01-01T00:00:00Z',
      last_seen_at: '2024-06-01T00:00:00Z',
      occurrence_count: 10,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-06-01T00:00:00Z',
      recent_events: [],
    };

    it('fetches entity detail when ID is provided', async () => {
      (apiClient.entities.getById as ReturnType<typeof vi.fn>).mockResolvedValueOnce(mockEntityDetail);

      const { result } = renderHook(() => useEntity('entity-1'), { wrapper });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.data).toEqual(mockEntityDetail);
      expect(apiClient.entities.getById).toHaveBeenCalledWith('entity-1', undefined);
    });

    it('does not fetch when ID is null', () => {
      const { result } = renderHook(() => useEntity(null), { wrapper });

      expect(result.current.isLoading).toBe(false);
      expect(apiClient.entities.getById).not.toHaveBeenCalled();
    });

    it('passes event limit to API', async () => {
      (apiClient.entities.getById as ReturnType<typeof vi.fn>).mockResolvedValueOnce(mockEntityDetail);

      const { result } = renderHook(() => useEntity('entity-1', 20), { wrapper });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(apiClient.entities.getById).toHaveBeenCalledWith('entity-1', 20);
    });
  });

  describe('useUpdateEntity', () => {
    const updatedEntity = {
      id: 'entity-1',
      entity_type: 'person',
      name: 'Updated Name',
      first_seen_at: '2024-01-01T00:00:00Z',
      last_seen_at: '2024-06-01T00:00:00Z',
      occurrence_count: 10,
    };

    it('updates entity name successfully', async () => {
      (apiClient.entities.update as ReturnType<typeof vi.fn>).mockResolvedValueOnce(updatedEntity);

      const { result } = renderHook(() => useUpdateEntity(), { wrapper });

      await result.current.mutateAsync({
        entityId: 'entity-1',
        name: 'Updated Name',
      });

      expect(apiClient.entities.update).toHaveBeenCalledWith('entity-1', { name: 'Updated Name' });
    });

    it('handles update error', async () => {
      const error = new Error('Update failed');
      (apiClient.entities.update as ReturnType<typeof vi.fn>).mockRejectedValueOnce(error);

      const { result } = renderHook(() => useUpdateEntity(), { wrapper });

      await expect(
        result.current.mutateAsync({
          entityId: 'entity-1',
          name: 'New Name',
        })
      ).rejects.toThrow('Update failed');
    });
  });

  describe('useDeleteEntity', () => {
    it('deletes entity successfully', async () => {
      (apiClient.entities.delete as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined);

      const { result } = renderHook(() => useDeleteEntity(), { wrapper });

      await result.current.mutateAsync('entity-1');

      expect(apiClient.entities.delete).toHaveBeenCalledWith('entity-1');
    });

    it('handles delete error', async () => {
      const error = new Error('Delete failed');
      (apiClient.entities.delete as ReturnType<typeof vi.fn>).mockRejectedValueOnce(error);

      const { result } = renderHook(() => useDeleteEntity(), { wrapper });

      await expect(result.current.mutateAsync('entity-1')).rejects.toThrow('Delete failed');
    });
  });
});
