/**
 * DeleteEntityDialog component tests (Story P4-3.6)
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DeleteEntityDialog } from '@/components/entities/DeleteEntityDialog';
import { apiClient } from '@/lib/api-client';
import type { IEntity } from '@/types/entity';

// Mock the API client
vi.mock('@/lib/api-client', () => ({
  apiClient: {
    entities: {
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

// Mock sonner toast
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe('DeleteEntityDialog', () => {
  const mockEntity: IEntity = {
    id: 'entity-123',
    entity_type: 'person',
    name: 'John Doe',
    first_seen_at: '2024-01-15T10:30:00Z',
    last_seen_at: '2024-06-20T14:45:00Z',
    occurrence_count: 15,
  };

  const mockOnClose = vi.fn();
  const mockOnDeleted = vi.fn();

  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
  });

  const renderWithProviders = (ui: React.ReactElement) => {
    return render(
      <QueryClientProvider client={queryClient}>
        {ui}
      </QueryClientProvider>
    );
  };

  it('renders dialog when open', () => {
    renderWithProviders(
      <DeleteEntityDialog
        entity={mockEntity}
        open={true}
        onClose={mockOnClose}
        onDeleted={mockOnDeleted}
      />
    );

    // Use getAllByText since "Delete Entity" appears in both title and button
    expect(screen.getAllByText('Delete Entity').length).toBeGreaterThan(0);
    expect(screen.getByText(/Are you sure you want to delete/)).toBeInTheDocument();
    expect(screen.getByText('John Doe')).toBeInTheDocument();
  });

  it('does not render when closed', () => {
    renderWithProviders(
      <DeleteEntityDialog
        entity={mockEntity}
        open={false}
        onClose={mockOnClose}
        onDeleted={mockOnDeleted}
      />
    );

    expect(screen.queryByText(/Are you sure you want to delete/)).not.toBeInTheDocument();
  });

  it('displays occurrence count in dialog', () => {
    renderWithProviders(
      <DeleteEntityDialog
        entity={mockEntity}
        open={true}
        onClose={mockOnClose}
        onDeleted={mockOnDeleted}
      />
    );

    expect(screen.getByText(/This entity has been seen 15 times/)).toBeInTheDocument();
  });

  it('shows warning about unlinking events', () => {
    renderWithProviders(
      <DeleteEntityDialog
        entity={mockEntity}
        open={true}
        onClose={mockOnClose}
        onDeleted={mockOnDeleted}
      />
    );

    expect(
      screen.getByText(/This will unlink this entity from all associated events/)
    ).toBeInTheDocument();
  });

  it('calls onClose when Cancel is clicked', () => {
    renderWithProviders(
      <DeleteEntityDialog
        entity={mockEntity}
        open={true}
        onClose={mockOnClose}
        onDeleted={mockOnDeleted}
      />
    );

    const cancelButton = screen.getByRole('button', { name: /Cancel/i });
    fireEvent.click(cancelButton);

    expect(mockOnClose).toHaveBeenCalledTimes(1);
  });

  it('calls API delete and callbacks on confirm', async () => {
    (apiClient.entities.delete as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined);

    renderWithProviders(
      <DeleteEntityDialog
        entity={mockEntity}
        open={true}
        onClose={mockOnClose}
        onDeleted={mockOnDeleted}
      />
    );

    const deleteButton = screen.getByRole('button', { name: /Delete Entity/i });
    fireEvent.click(deleteButton);

    await waitFor(() => {
      expect(apiClient.entities.delete).toHaveBeenCalledWith('entity-123');
    });

    await waitFor(() => {
      expect(mockOnDeleted).toHaveBeenCalled();
      expect(mockOnClose).toHaveBeenCalled();
    });
  });

  it('shows loading state during deletion', async () => {
    // Make the delete hang
    (apiClient.entities.delete as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise(() => {})
    );

    renderWithProviders(
      <DeleteEntityDialog
        entity={mockEntity}
        open={true}
        onClose={mockOnClose}
        onDeleted={mockOnDeleted}
      />
    );

    const deleteButton = screen.getByRole('button', { name: /Delete Entity/i });
    fireEvent.click(deleteButton);

    await waitFor(() => {
      expect(screen.getByText(/Deleting/)).toBeInTheDocument();
    });
  });
});
