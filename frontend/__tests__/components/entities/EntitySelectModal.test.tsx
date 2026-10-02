/**
 * EntitySelectModal shows unnamed vehicles by their stored details.
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { EntitySelectModal } from '@/components/entities/EntitySelectModal';

const { useEntitiesMock } = vi.hoisted(() => ({
  useEntitiesMock: vi.fn(),
}));

vi.mock('@/hooks/useEntities', () => ({
  useEntities: (...args: unknown[]) => useEntitiesMock(...args),
}));

vi.mock('sonner', () => ({
  toast: {
    info: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const tesla = {
  id: '1c915ee6-aaaa-bbbb-cccc-ddddeeeeffff',
  entity_type: 'vehicle' as const,
  name: null,
  occurrence_count: 4,
  first_seen_at: '2026-09-01T12:00:00Z',
  last_seen_at: '2026-09-30T12:00:00Z',
  vehicle_color: 'red',
  vehicle_make: 'tesla',
  vehicle_model: 'model y',
  vehicle_signature: 'red-tesla-modely',
};

const kia = {
  id: 'bbbbbbbb-aaaa-bbbb-cccc-ddddeeeeffff',
  entity_type: 'vehicle' as const,
  name: null,
  occurrence_count: 1,
  first_seen_at: '2026-09-01T12:00:00Z',
  last_seen_at: '2026-09-30T12:00:00Z',
  vehicle_color: 'black',
  vehicle_make: 'kia',
  vehicle_model: 'seltos',
};

const alice = {
  id: 'cccccccc-aaaa-bbbb-cccc-ddddeeeeffff',
  entity_type: 'person' as const,
  name: 'Alice',
  occurrence_count: 2,
  first_seen_at: '2026-09-01T12:00:00Z',
  last_seen_at: '2026-09-30T12:00:00Z',
};

describe('EntitySelectModal vehicle labels', () => {
  const onSelect = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    useEntitiesMock.mockReturnValue({
      data: { entities: [tesla, kia, alice], total: 3 },
      isLoading: false,
    });
  });

  it('renders an unnamed vehicle as its color, make, and model', () => {
    render(
      <EntitySelectModal open onOpenChange={vi.fn()} onSelect={onSelect} />
    );

    expect(screen.getByText('Red Tesla Model Y')).toBeInTheDocument();
    expect(screen.getByText('Black Kia Seltos')).toBeInTheDocument();
    expect(screen.queryByText(/Vehicle #1c915ee6/)).not.toBeInTheDocument();
  });

  it('filters the list when the search matches a vehicle make', () => {
    render(
      <EntitySelectModal open onOpenChange={vi.fn()} onSelect={onSelect} />
    );

    fireEvent.change(screen.getByPlaceholderText('Search entities...'), {
      target: { value: 'tesla' },
    });

    expect(screen.getByText('Red Tesla Model Y')).toBeInTheDocument();
    expect(screen.queryByText('Black Kia Seltos')).not.toBeInTheDocument();
    expect(screen.queryByText('Alice')).not.toBeInTheDocument();
    expect(useEntitiesMock).toHaveBeenCalledWith(
      expect.objectContaining({ search: 'tesla' })
    );
  });

  it('uses the vehicle descriptor in the assignment confirmation', () => {
    render(
      <EntitySelectModal open onOpenChange={vi.fn()} onSelect={onSelect} />
    );

    fireEvent.click(screen.getByRole('button', { name: /Red Tesla Model Y/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    expect(screen.getByRole('alertdialog')).toHaveTextContent('Red Tesla Model Y');
    expect(screen.getByText(/will trigger AI re-classification/)).toBeInTheDocument();
  });
});
