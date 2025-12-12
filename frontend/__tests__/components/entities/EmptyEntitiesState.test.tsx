/**
 * EmptyEntitiesState component tests (Story P4-3.6)
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { EmptyEntitiesState } from '@/components/entities/EmptyEntitiesState';

describe('EmptyEntitiesState', () => {
  it('renders default empty state message when no filters', () => {
    render(<EmptyEntitiesState />);

    expect(screen.getByText('No recognized entities yet')).toBeInTheDocument();
    expect(
      screen.getByText(/Entities are automatically created when the same person or vehicle/)
    ).toBeInTheDocument();
  });

  it('renders filtered empty state when hasFilters is true', () => {
    render(<EmptyEntitiesState hasFilters={true} />);

    expect(screen.getByText('No matching entities')).toBeInTheDocument();
    expect(
      screen.getByText(/No entities match your current filters/)
    ).toBeInTheDocument();
  });

  it('shows Clear Filters button when filters applied and onClearFilters provided', () => {
    const mockClearFilters = vi.fn();

    render(
      <EmptyEntitiesState
        hasFilters={true}
        onClearFilters={mockClearFilters}
      />
    );

    const clearButton = screen.getByRole('button', { name: /Clear Filters/i });
    expect(clearButton).toBeInTheDocument();
  });

  it('calls onClearFilters when Clear Filters button is clicked', () => {
    const mockClearFilters = vi.fn();

    render(
      <EmptyEntitiesState
        hasFilters={true}
        onClearFilters={mockClearFilters}
      />
    );

    const clearButton = screen.getByRole('button', { name: /Clear Filters/i });
    fireEvent.click(clearButton);

    expect(mockClearFilters).toHaveBeenCalledTimes(1);
  });

  it('does not show Clear Filters button when no filters applied', () => {
    render(<EmptyEntitiesState hasFilters={false} />);

    expect(screen.queryByRole('button', { name: /Clear Filters/i })).not.toBeInTheDocument();
  });
});
