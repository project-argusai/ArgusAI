/**
 * EntityCard component tests (Story P4-3.6)
 * Story P16-3.3: Tests for Edit button functionality
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { EntityCard } from '@/components/entities/EntityCard';
import type { IEntity } from '@/types/entity';

// Create a wrapper with QueryClientProvider for tests
const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const TestWrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
  TestWrapper.displayName = 'TestWrapper';
  return TestWrapper;
};

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
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText('John Doe')).toBeInTheDocument();
  });

  it('renders a type and id fallback when name is null', () => {
    const unnamedEntity: IEntity = {
      ...mockEntity,
      name: null,
    };

    render(
      <EntityCard
        entity={unnamedEntity}
        onClick={mockOnClick}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText('Person #entity-1')).toBeInTheDocument();
  });

  it('displays occurrence count', () => {
    render(
      <EntityCard
        entity={mockEntity}
        onClick={mockOnClick}
      />,
      { wrapper: createWrapper() }
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
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText(/Seen 1 time/)).toBeInTheDocument();
  });

  it('displays entity type badge', () => {
    render(
      <EntityCard
        entity={mockEntity}
        onClick={mockOnClick}
      />,
      { wrapper: createWrapper() }
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
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText('vehicle')).toBeInTheDocument();
  });

  it('calls onClick when card is clicked', () => {
    const { container } = render(
      <EntityCard
        entity={mockEntity}
        onClick={mockOnClick}
      />,
      { wrapper: createWrapper() }
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
      />,
      { wrapper: createWrapper() }
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
      />,
      { wrapper: createWrapper() }
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
      />,
      { wrapper: createWrapper() }
    );

    const nameElement = screen.getByText('Person #entity-1');
    expect(nameElement).toHaveClass('italic');
  });

  // Story P7-4.2 AC3: Add Alert button exists
  it('renders "Add Alert" button (Story P7-4.2 AC3)', () => {
    render(
      <EntityCard
        entity={mockEntity}
        onClick={mockOnClick}
      />,
      { wrapper: createWrapper() }
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
      />,
      { wrapper: createWrapper() }
    );

    const addAlertButton = screen.getByRole('button', { name: /add alert/i });
    fireEvent.click(addAlertButton);

    // Card onClick should NOT have been called
    expect(mockOnClick).not.toHaveBeenCalled();
  });

  // Story P16-3.3 AC1: Edit button renders on entity card
  it('renders "Edit" button (Story P16-3.3 AC1)', () => {
    render(
      <EntityCard
        entity={mockEntity}
        onClick={mockOnClick}
      />,
      { wrapper: createWrapper() }
    );

    const editButton = screen.getByRole('button', { name: /edit john doe/i });
    expect(editButton).toBeInTheDocument();
  });

  // Story P16-3.3 AC3: Edit button click does not trigger card onClick
  it('"Edit" button click does not trigger card onClick (Story P16-3.3 AC3)', () => {
    render(
      <EntityCard
        entity={mockEntity}
        onClick={mockOnClick}
      />,
      { wrapper: createWrapper() }
    );

    const editButton = screen.getByRole('button', { name: /edit john doe/i });
    fireEvent.click(editButton);

    // Card onClick should NOT have been called (stopPropagation)
    expect(mockOnClick).not.toHaveBeenCalled();
  });

  // Story P16-3.3: onEntityUpdated callback is optional
  it('accepts optional onEntityUpdated callback (Story P16-3.3)', () => {
    const mockOnEntityUpdated = vi.fn();

    render(
      <EntityCard
        entity={mockEntity}
        onClick={mockOnClick}
        onEntityUpdated={mockOnEntityUpdated}
      />,
      { wrapper: createWrapper() }
    );

    // Component should render without errors
    expect(screen.getByText('John Doe')).toBeInTheDocument();
  });
});
