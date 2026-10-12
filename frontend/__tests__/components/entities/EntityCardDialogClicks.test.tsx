/**
 * Regression: clicks inside the Edit Entity dialog must not bubble to the
 * card's onClick (which opens the entity event view).
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi } from 'vitest';
import { EntityCard } from '@/components/entities/EntityCard';
import type { IEntity } from '@/types/entity';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/entities/EntityPlateSection', () => ({
  EntityPlateSection: () => <input aria-label="Plate" placeholder="plate" />,
}));

const entity: IEntity = {
  id: 'entity-1',
  entity_type: 'vehicle',
  name: 'Test Car',
  first_seen_at: '2024-01-15T10:30:00Z',
  last_seen_at: '2024-06-20T14:45:00Z',
  occurrence_count: 3,
};

describe('EntityCard edit dialog click isolation', () => {
  it('does not call card onClick for clicks inside the dialog; plate input accepts typing', async () => {
    const onClick = vi.fn();
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <EntityCard entity={entity} onClick={onClick} />
      </QueryClientProvider>
    );
    fireEvent.click(screen.getByRole('button', { name: /edit/i }));
    expect(onClick).not.toHaveBeenCalled();

    const dialog = await screen.findByRole('dialog');
    fireEvent.click(dialog);
    const nameInput = screen.getByDisplayValue('Test Car');
    fireEvent.click(nameInput);
    const plate = screen.getByLabelText('Plate');
    await userEvent.click(plate);
    expect(plate).toHaveFocus();
    await userEvent.type(plate, 'ABC123');
    expect(plate).toHaveValue('ABC123');
    expect(onClick).not.toHaveBeenCalled();
  });
});
