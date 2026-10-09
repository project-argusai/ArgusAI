/**
 * EntityPlateSection tests. Plate values here are obviously fake.
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { EntityPlateSection } from '@/components/entities/EntityPlateSection';
import { apiClient } from '@/lib/api-client';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/lib/api-client', async (orig) => {
  const actual = await orig<typeof import('@/lib/api-client')>();
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      entities: {
        ...actual.apiClient.entities,
        plateStatus: vi.fn(),
        listPlates: vi.fn(),
        addPlate: vi.fn(),
        removePlate: vi.fn(),
      },
    },
  };
});

const entities = apiClient.entities as unknown as Record<string, ReturnType<typeof vi.fn>>;

function renderSection(entityType = 'vehicle') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <EntityPlateSection entityId="veh-1" entityType={entityType} />
    </QueryClientProvider>
  );
}

const enabled = { enabled: true, salt_configured: true, active: true };

describe('EntityPlateSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    entities.plateStatus.mockResolvedValue(enabled);
    entities.listPlates.mockResolvedValue({ entity_id: 'veh-1', plates: [] });
    entities.addPlate.mockResolvedValue({ status: 'enrolled' });
    entities.removePlate.mockResolvedValue({ deleted_count: 1 });
  });

  it('is hidden when plate recognition is disabled', async () => {
    entities.plateStatus.mockResolvedValue({ ...enabled, enabled: false });
    renderSection();
    await waitFor(() => expect(entities.plateStatus).toHaveBeenCalled());
    expect(screen.queryByTestId('entity-plate-section')).not.toBeInTheDocument();
  });

  it('is hidden for non-vehicles without calling the API', () => {
    renderSection('person');
    expect(screen.queryByTestId('entity-plate-section')).not.toBeInTheDocument();
    expect(entities.plateStatus).not.toHaveBeenCalled();
  });

  it('shows a password-style input when enabled', async () => {
    renderSection();
    const input = await screen.findByLabelText(/license plate/i);
    expect(input).toHaveAttribute('type', 'password');
    expect(input).toHaveAttribute('autocomplete', 'off');
    expect(screen.queryByTestId('plate-on-file')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /remove plate/i })).not.toBeInTheDocument();
  });

  it('submits the plate then clears the input and stores nothing', async () => {
    const user = userEvent.setup();
    renderSection();
    const input = (await screen.findByLabelText(/license plate/i)) as HTMLInputElement;
    await user.type(input, 'ABC123');
    await user.click(screen.getByRole('button', { name: /save plate/i }));
    await waitFor(() => expect(entities.addPlate).toHaveBeenCalledWith('veh-1', 'ABC123'));
    expect(input.value).toBe('');
    expect(JSON.stringify({ ...localStorage })).not.toContain('ABC123');
    expect(JSON.stringify({ ...sessionStorage })).not.toContain('ABC123');
    expect(document.body.innerHTML).not.toContain('ABC123');
  });

  it('clears the input even when saving fails, without echoing it', async () => {
    const { toast } = await import('sonner');
    entities.addPlate.mockRejectedValue(new Error('boom ABC123'));
    const user = userEvent.setup();
    renderSection();
    const input = (await screen.findByLabelText(/license plate/i)) as HTMLInputElement;
    await user.type(input, 'ABC123');
    await user.click(screen.getByRole('button', { name: /save plate/i }));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(input.value).toBe('');
    expect(JSON.stringify(vi.mocked(toast.error).mock.calls)).not.toContain('ABC123');
  });

  it('does not submit an empty value', async () => {
    const user = userEvent.setup();
    renderSection();
    await screen.findByLabelText(/license plate/i);
    await user.click(screen.getByRole('button', { name: /save plate/i }));
    expect(entities.addPlate).not.toHaveBeenCalled();
  });

  it('shows "Plate on file" only, and removes it', async () => {
    entities.listPlates.mockResolvedValue({
      entity_id: 'veh-1',
      plates: [{ id: 'p-1', entity_id: 'veh-1', usable: true }],
    });
    const user = userEvent.setup();
    renderSection();
    expect(await screen.findByTestId('plate-on-file')).toHaveTextContent('Plate on file');
    await user.click(screen.getByRole('button', { name: /remove plate/i }));
    await waitFor(() => expect(entities.removePlate).toHaveBeenCalledWith('veh-1', 'p-1'));
  });
});
