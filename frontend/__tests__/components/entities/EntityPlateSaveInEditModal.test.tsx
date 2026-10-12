/**
 * Regression: the real EntityPlateSection inside the real EntityEditModal must
 * POST the plate (it used to be a <form> nested inside the edit <form>).
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { EntityEditModal, type EntityEditData } from '@/components/entities/EntityEditModal';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const ENTITY_ID = 'veh-1';
const entity: EntityEditData = {
  id: ENTITY_ID,
  entity_type: 'vehicle',
  name: 'Test Car',
  notes: null,
  is_vip: false,
  is_blocked: false,
  thumbnail_path: null,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('plate save inside EntityEditModal', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  const onOpenChange = vi.fn();

  beforeEach(() => {
    onOpenChange.mockReset();
    fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      if (url.endsWith('/context/plates/status')) return json({ enabled: true, available: true });
      if (url.endsWith(`/context/entities/${ENTITY_ID}/plates`) && method === 'GET')
        return json({ entity_id: ENTITY_ID, plates: [] });
      if (url.endsWith(`/context/entities/${ENTITY_ID}/plates`) && method === 'POST')
        return json({ status: 'saved' }, 201);
      return json({ ...entity });
    });
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  function setup() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <EntityEditModal open onOpenChange={onOpenChange} entity={entity} />
      </QueryClientProvider>
    );
  }

  const posts = () =>
    fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST');
  const entityUpdates = () =>
    fetchMock.mock.calls.filter(([, init]) => ['PUT', 'PATCH'].includes((init as RequestInit | undefined)?.method ?? ''));

  it.each([
    ['click', async (u: ReturnType<typeof userEvent.setup>) => u.click(screen.getByRole('button', { name: 'Save plate' }))],
    ['Enter', async (u: ReturnType<typeof userEvent.setup>) => u.keyboard('{Enter}')],
  ])('POSTs the plate on %s without saving or closing the edit dialog', async (_n, act) => {
    const user = userEvent.setup();
    setup();
    const input = await screen.findByLabelText(/license plate/i);
    await user.type(input, 'ABC123');
    await act(user);
    await waitFor(() => expect(posts()).toHaveLength(1));
    const [url, init] = posts()[0];
    expect(String(url)).toMatch(new RegExp(`/api/v1/context/entities/${ENTITY_ID}/plates$`));
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ plate: 'ABC123' });
    expect(entityUpdates()).toHaveLength(0);
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
    expect((input as HTMLInputElement).value).toBe('');
  });
});
