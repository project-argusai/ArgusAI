/**
 * Regression: the entities page must not refetch GET /context/entities in a loop.
 *
 * router.replace is a navigation. On this app, calling it for a URL that is
 * already current shows app/loading.tsx and remounts the providers above the
 * page (the same failure fixed on the events page). A new QueryClient then
 * fetches the list again, the effect runs again, and the page flickers.
 *
 * This harness models that: every replace() remounts the provider tree.
 */

import React, { useLayoutEffect, useState } from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import EntitiesPage from '@/app/entities/page';
import { apiClient } from '@/lib/api-client';

const navigation = vi.hoisted(() => {
  const state = {
    searchParams: new URLSearchParams(),
    navs: 0,
    scheduleRemount: null as null | (() => void),
    replace(url: string) {
      const query = url.includes('?') ? url.slice(url.indexOf('?') + 1) : '';
      state.searchParams = new URLSearchParams(query);
      state.navs += 1;
      // Cap the loop so a regression fails the assertion instead of hanging.
      if (state.navs <= 8) {
        state.scheduleRemount?.();
      }
    },
  };
  return state;
});

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: navigation.replace,
    push: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
  }),
  useSearchParams: () => navigation.searchParams,
  usePathname: () => '/entities',
  useParams: () => ({}),
}));

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    entities: {
      list: vi.fn(),
      get: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
      create: vi.fn(),
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

const entity = {
  id: 'entity-1',
  entity_type: 'person',
  name: 'Ada Lovelace',
  thumbnail_path: null,
  first_seen_at: '2024-01-15T10:30:00Z',
  last_seen_at: '2024-06-20T14:45:00Z',
  occurrence_count: 4,
};

function ProviderTree({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: false },
          mutations: { retry: false },
        },
      })
  );
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

function Harness() {
  const [epoch, setEpoch] = useState(0);
  // Layout effect runs before the list's passive URL effect, so a replace
  // on mount can remount this tree the way Next's navigation does.
  useLayoutEffect(() => {
    navigation.scheduleRemount = () => {
      setEpoch((n) => n + 1);
    };
    return () => {
      navigation.scheduleRemount = null;
    };
  });
  return (
    <ProviderTree key={epoch}>
      <EntitiesPage />
    </ProviderTree>
  );
}

describe('Entities page list query', () => {
  beforeEach(() => {
    navigation.searchParams = new URLSearchParams();
    navigation.navs = 0;
    navigation.scheduleRemount = null;
    vi.clearAllMocks();
    vi.mocked(apiClient.entities.list).mockResolvedValue({
      entities: [entity],
      total: 1,
    });
    vi.mocked(apiClient.entities.get).mockResolvedValue({
      ...entity,
      notes: null,
      is_vip: false,
      is_blocked: false,
      created_at: '2024-01-15T10:30:00Z',
      updated_at: '2024-06-20T14:45:00Z',
      recent_events: [],
    });
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        statusText: 'OK',
        json: async () => ({
          entity_id: entity.id,
          events: [],
          total: 0,
          page: 1,
          limit: 50,
          has_more: false,
        }),
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('does not refetch the list on mount or when an entity card opens the detail modal', async () => {
    render(<Harness />);

    expect(await screen.findByRole('heading', { name: 'Ada Lovelace' })).toBeInTheDocument();

    // The broken effect calls router.replace on mount, which remounts the
    // providers and fetches again. Give that cycle time to spin.
    await new Promise((resolve) => setTimeout(resolve, 400));

    expect(navigation.navs).toBe(0);
    expect(apiClient.entities.list).toHaveBeenCalledTimes(1);
    expect(apiClient.entities.list).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 50, offset: 0 })
    );

    fireEvent.click(screen.getByRole('heading', { name: 'Ada Lovelace' }));

    await waitFor(() => {
      expect(apiClient.entities.get).toHaveBeenCalledWith('entity-1');
    });

    await new Promise((resolve) => setTimeout(resolve, 400));

    expect(navigation.navs).toBe(0);
    expect(apiClient.entities.list).toHaveBeenCalledTimes(1);
  });

  it('writes a changed search to the URL once', async () => {
    render(<Harness />);

    expect(await screen.findByRole('heading', { name: 'Ada Lovelace' })).toBeInTheDocument();

    fireEvent.change(screen.getByRole('textbox', { name: 'Search entities by name' }), {
      target: { value: 'Bob' },
    });

    await waitFor(() => {
      expect(navigation.navs).toBe(1);
    });

    expect(navigation.searchParams.get('search')).toBe('Bob');
    // Debouncing the search changes the list query key (second fetch) and the
    // navigation remounts the providers (third fetch). It must stop there.
    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(navigation.navs).toBe(1);
    expect(apiClient.entities.list).toHaveBeenCalledTimes(3);
    expect(apiClient.entities.list).toHaveBeenLastCalledWith(
      expect.objectContaining({ limit: 50, search: 'Bob' })
    );
  });
});
