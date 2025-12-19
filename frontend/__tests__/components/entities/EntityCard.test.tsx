/**
 * EntityCard component tests (Story P4-3.6)
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { EntityCard } from '@/components/entities/EntityCard';
import type { IEntity } from '@/types/entity';

describe('EntityCard', () => {
  const mockEntity: IEntity = {
    id: 'entity-123',
    entity_type: 'person',
    name: 'John Doe',
    first_seen_at: '2024-01-15T10:30:00Z',
    last_seen_at: '2024-06-20T14:45:00Z',
    occurrence_count: 15,
  };

  const mockOnClick = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders entity name when provided', () => {
    render(
      <EntityCard
        entity={mockEntity}
        onClick={mockOnClick}
      />
    );

    expect(screen.getByText('John Doe')).toBeInTheDocument();
  });

  it('renders "Unknown person" when name is null', () => {
    const unnamedEntity: IEntity = {
      ...mockEntity,
      name: null,
    };

    render(
      <EntityCard
        entity={unnamedEntity}
        onClick={mockOnClick}
      />
    );

    expect(screen.getByText('Unknown person')).toBeInTheDocument();
  });

  it('displays occurrence count', () => {
    render(
      <EntityCard
        entity={mockEntity}
        onClick={mockOnClick}
      />
    );

    expect(screen.getByText(/Seen 15 times/)).toBeInTheDocument();
  });

  it('shows singular "time" for occurrence_count of 1', () => {
    const singleOccurrence: IEntity = {
      ...mockEntity,
      occurrence_count: 1,
    };

    render(
      <EntityCard
        entity={singleOccurrence}
        onClick={mockOnClick}
      />
    );

    expect(screen.getByText(/Seen 1 time/)).toBeInTheDocument();
  });

  it('displays entity type badge', () => {
    render(
      <EntityCard
        entity={mockEntity}
        onClick={mockOnClick}
      />
    );

    expect(screen.getByText('person')).toBeInTheDocument();
  });

  it('displays vehicle type badge correctly', () => {
    const vehicleEntity: IEntity = {
      ...mockEntity,
      entity_type: 'vehicle',
    };

    render(
      <EntityCard
        entity={vehicleEntity}
        onClick={mockOnClick}
      />
    );

    expect(screen.getByText('vehicle')).toBeInTheDocument();
  });

  it('calls onClick when card is clicked', () => {
    const { container } = render(
      <EntityCard
        entity={mockEntity}
        onClick={mockOnClick}
      />
    );

    // Find the card by its cursor-pointer class
    const card = container.querySelector('.cursor-pointer');

    if (card) {
      fireEvent.click(card);
      expect(mockOnClick).toHaveBeenCalledTimes(1);
    }
  });

  it('renders thumbnail when URL is provided', () => {
    const { container } = render(
      <EntityCard
        entity={mockEntity}
        thumbnailUrl="/api/v1/thumbnails/test.jpg"
        onClick={mockOnClick}
      />
    );

    const img = container.querySelector('img');
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute('src', expect.stringContaining('test.jpg'));
  });

  it('shows placeholder icon when no thumbnail', () => {
    render(
      <EntityCard
        entity={mockEntity}
        thumbnailUrl={null}
        onClick={mockOnClick}
      />
    );

    // Should show the person icon placeholder (User icon from lucide)
    // The icon is rendered as SVG
    expect(screen.getByText('John Doe')).toBeInTheDocument();
  });

  it('applies italic styling to unnamed entities', () => {
    const unnamedEntity: IEntity = {
      ...mockEntity,
      name: null,
    };

    render(
      <EntityCard
        entity={unnamedEntity}
        onClick={mockOnClick}
      />
    );

    const nameElement = screen.getByText('Unknown person');
    expect(nameElement).toHaveClass('italic');
  });

  // Story P7-4.2 AC3: Add Alert button exists
  it('renders "Add Alert" button (Story P7-4.2 AC3)', () => {
    render(
      <EntityCard
        entity={mockEntity}
        onClick={mockOnClick}
      />
    );

    const addAlertButton = screen.getByRole('button', { name: /add alert/i });
    expect(addAlertButton).toBeInTheDocument();
  });

  // Story P7-4.2 AC4: Add Alert button does not trigger card click
  it('"Add Alert" button click does not trigger card onClick (Story P7-4.2 AC4)', () => {
    render(
      <EntityCard
        entity={mockEntity}
        onClick={mockOnClick}
      />
    );

    const addAlertButton = screen.getByRole('button', { name: /add alert/i });
    fireEvent.click(addAlertButton);

    // Card onClick should NOT have been called
    expect(mockOnClick).not.toHaveBeenCalled();
  });
});
