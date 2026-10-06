/**
 * Several entities on one event (issue #652): chips, remove, add, picker.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { EventEntities, eventEntitiesOf } from '@/components/events/EventEntities';
import { SKIP_ENTITY_ASSIGN_WARNING_KEY } from '@/components/entities/EntityAssignConfirmDialog';
import type { IEvent, IEventEntity } from '@/types/event';

const { useEntitiesMock, reanalyzeMock } = vi.hoisted(() => ({
  useEntitiesMock: vi.fn(),
  reanalyzeMock: vi.fn(),
}));

vi.mock('@/hooks/useEntities', async () => {
  const actual = await vi.importActual<typeof import('@/hooks/useEntities')>(
    '@/hooks/useEntities'
  );
  return { ...actual, useEntities: (...args: unknown[]) => useEntitiesMock(...args) };
});

vi.mock('@/lib/api-client', () => ({
  apiClient: { events: { reanalyze: (...args: unknown[]) => reanalyzeMock(...args) } },
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

const isaac: IEventEntity = {
  id: 'isaac',
  name: 'Isaac',
  entity_type: 'person',
  is_primary: true,
  linked: true,
};

const bmw: IEventEntity = {
  id: 'bmw-x3',
  name: null,
  entity_type: 'vehicle',
  vehicle_color: 'black',
  vehicle_make: 'BMW',
  vehicle_model: 'X3',
  linked: true,
};

const brent = {
  id: '42',
  entity_type: 'person' as const,
  name: 'Brent',
  occurrence_count: 3,
  first_seen_at: '2026-09-01T12:00:00Z',
  last_seen_at: '2026-10-01T12:00:00Z',
};

const makeEvent = (overrides: Partial<IEvent> = {}): IEvent => ({
  id: 'evt-1',
  camera_id: 'cam-1',
  camera_name: 'Driveway',
  timestamp: '2026-10-05T18:00:00Z',
  description: 'Isaac walks to his car.',
  thumbnail_base64: null,
  objects_detected: ['person', 'vehicle'],
  confidence: 90,
  ...overrides,
} as IEvent);

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })
  );
}

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const chipIds = () =>
  screen.queryAllByTestId('event-entity-chip').map((chip) => chip.getAttribute('data-entity-id'));

describe('EventEntities', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    localStorage.setItem(SKIP_ENTITY_ASSIGN_WARNING_KEY, 'true');
    useEntitiesMock.mockReturnValue({
      data: {
        entities: [
          { ...isaac, occurrence_count: 4, first_seen_at: '', last_seen_at: '' },
          { ...bmw, occurrence_count: 6, first_seen_at: '', last_seen_at: '' },
          brent,
        ],
        total: 3,
      },
      isLoading: false,
    });
    reanalyzeMock.mockResolvedValue({ ...makeEvent(), description: 'Brent walks.' });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('shows one chip per entity, person and vehicle', () => {
    renderWithClient(<EventEntities event={makeEvent({ entities: [isaac, bmw] })} />);

    expect(chipIds()).toEqual(['isaac', 'bmw-x3']);
    expect(screen.getByText('Isaac')).toBeInTheDocument();
    expect(screen.getByText('Black Bmw X3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove Isaac from this event' })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Remove Black Bmw X3 from this event' })
    ).toBeInTheDocument();
  });

  it('falls back to the legacy single-entity fields', () => {
    const event = makeEvent({ entity_id: 'isaac', entity_name: 'Isaac', entity_type: 'person' });
    expect(eventEntitiesOf(event).map((e) => e.id)).toEqual(['isaac']);
    expect(eventEntitiesOf(makeEvent())).toEqual([]);
  });

  it('removing one chip keeps the other and does not open the card', async () => {
    const user = userEvent.setup();
    const onCardClick = vi.fn();
    fetchMock.mockImplementation(() =>
      jsonResponse({ success: true, message: 'Event removed from entity', entities: [isaac] })
    );

    renderWithClient(
      <div onClick={onCardClick}>
        <EventEntities event={makeEvent({ entities: [isaac, bmw] })} />
      </div>
    );
    await user.click(screen.getByRole('button', { name: 'Remove Black Bmw X3 from this event' }));

    await waitFor(() => expect(chipIds()).toEqual(['isaac']));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/context/entities/bmw-x3/events/evt-1');
    expect(init.method).toBe('DELETE');
    expect(onCardClick).not.toHaveBeenCalled();
  });

  it('adds an entity without removing the others, sending the id as a string', async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(() =>
      jsonResponse({
        success: true,
        message: 'Event added to Brent',
        action: 'add',
        entity_id: '42',
        entity_name: 'Brent',
        entities: [isaac, bmw, { id: '42', name: 'Brent', entity_type: 'person' }],
      })
    );

    renderWithClient(<EventEntities event={makeEvent({ entities: [isaac, bmw] })} />);
    await user.click(screen.getByRole('button', { name: /Add to Entity/ }));

    // The picker hides entities already on the event.
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).queryByText('Isaac')).not.toBeInTheDocument();
    expect(within(dialog).queryByText('Black Bmw X3')).not.toBeInTheDocument();
    await user.click(within(dialog).getByText('Brent'));
    await user.click(within(dialog).getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(chipIds()).toEqual(['isaac', 'bmw-x3', '42']));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/context/events/evt-1/entity');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ entity_id: '42', replace: false });
    await waitFor(() => expect(reanalyzeMock).toHaveBeenCalledWith('evt-1', 'single_frame'));
  });

  it('disables Add at the per-event cap', () => {
    const four: IEventEntity[] = ['a', 'b', 'c', 'd'].map((id) => ({
      id,
      name: id.toUpperCase(),
      entity_type: 'person',
    }));
    renderWithClient(<EventEntities event={makeEvent({ entities: four })} />);

    expect(screen.getByRole('button', { name: /Add to Entity/ })).toBeDisabled();
  });
});
