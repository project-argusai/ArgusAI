/**
 * EntityEditModal component tests (Story P16-3.2)
 * Tests for editing entity properties modal
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { EntityEditModal, type EntityEditData } from '@/components/entities/EntityEditModal';

// Mock the useUpdateEntity hook
const mockMutateAsync = vi.fn();
vi.mock('@/hooks/useEntities', () => ({
  useUpdateEntity: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
}));

// Mock sonner toast
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe('EntityEditModal', () => {
  const mockEntity: EntityEditData = {
    id: 'entity-123',
    entity_type: 'person',
    name: 'John Doe',
    notes: 'Friendly neighbor',
    is_vip: false,
    is_blocked: false,
    thumbnail_path: '/thumbnails/test.jpg',
  };

  const mockOnOpenChange = vi.fn();
  const mockOnUpdated = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockMutateAsync.mockResolvedValue({ ...mockEntity });
  });

  it('renders modal when open is true', () => {
    render(
      <EntityEditModal
        open={true}
        onOpenChange={mockOnOpenChange}
        entity={mockEntity}
        onUpdated={mockOnUpdated}
      />
    );

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Edit Entity')).toBeInTheDocument();
  });

  it('does not render modal when open is false', () => {
    render(
      <EntityEditModal
        open={false}
        onOpenChange={mockOnOpenChange}
        entity={mockEntity}
        onUpdated={mockOnUpdated}
      />
    );

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  // AC2: Fields pre-filled with current entity values
  it('pre-fills form with entity values (AC2)', () => {
    render(
      <EntityEditModal
        open={true}
        onOpenChange={mockOnOpenChange}
        entity={mockEntity}
        onUpdated={mockOnUpdated}
      />
    );

    // Check name field
    const nameInput = screen.getByPlaceholderText(/Mail Carrier/i);
    expect(nameInput).toHaveValue('John Doe');

    // Check notes field
    const notesInput = screen.getByPlaceholderText(/additional notes/i);
    expect(notesInput).toHaveValue('Friendly neighbor');
  });

  // AC1: Form with all required fields
  it('renders all form fields (AC1)', () => {
    render(
      <EntityEditModal
        open={true}
        onOpenChange={mockOnOpenChange}
        entity={mockEntity}
        onUpdated={mockOnUpdated}
      />
    );

    // Name field
    expect(screen.getByLabelText(/^Name$/)).toBeInTheDocument();

    // Type field
    expect(screen.getByText(/^Type$/)).toBeInTheDocument();

    // VIP toggle - check for the label specifically
    expect(screen.getByText('Mark as a VIP for priority alerts')).toBeInTheDocument();

    // Blocked toggle - check for the description
    expect(screen.getByText('Block this entity from alerts')).toBeInTheDocument();

    // Notes field
    expect(screen.getByLabelText(/^Notes$/)).toBeInTheDocument();
  });

  // AC5: Entity thumbnail at top
  it('displays entity thumbnail (AC5)', () => {
    render(
      <EntityEditModal
        open={true}
        onOpenChange={mockOnOpenChange}
        entity={mockEntity}
        onUpdated={mockOnUpdated}
      />
    );

    const img = screen.getByRole('img');
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute('src', expect.stringContaining('/thumbnails/test.jpg'));
  });

  // AC3: Success toast and modal closes on save
  it('shows success toast and closes modal on save (AC3)', async () => {
    const user = userEvent.setup();
    const { toast } = await import('sonner');

    render(
      <EntityEditModal
        open={true}
        onOpenChange={mockOnOpenChange}
        entity={mockEntity}
        onUpdated={mockOnUpdated}
      />
    );

    const saveButton = screen.getByRole('button', { name: /Save/i });
    await user.click(saveButton);

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalled();
      expect(toast.success).toHaveBeenCalledWith('Entity updated');
      expect(mockOnOpenChange).toHaveBeenCalledWith(false);
      expect(mockOnUpdated).toHaveBeenCalled();
    });
  });

  // AC4: Cancel closes without saving
  it('closes modal without saving on Cancel (AC4)', async () => {
    const user = userEvent.setup();

    render(
      <EntityEditModal
        open={true}
        onOpenChange={mockOnOpenChange}
        entity={mockEntity}
        onUpdated={mockOnUpdated}
      />
    );

    const cancelButton = screen.getByRole('button', { name: /Cancel/i });
    await user.click(cancelButton);

    expect(mockMutateAsync).not.toHaveBeenCalled();
    expect(mockOnOpenChange).toHaveBeenCalledWith(false);
    expect(mockOnUpdated).not.toHaveBeenCalled();
  });

  // AC8: Modal can be closed via X button
  it('closes modal via close button (AC8)', async () => {
    const user = userEvent.setup();

    render(
      <EntityEditModal
        open={true}
        onOpenChange={mockOnOpenChange}
        entity={mockEntity}
        onUpdated={mockOnUpdated}
      />
    );

    // Find the close button (X button in dialog header)
    const closeButton = screen.getByRole('button', { name: /close/i });
    await user.click(closeButton);

    expect(mockOnOpenChange).toHaveBeenCalledWith(false);
  });

  it('calls mutateAsync with updated values', async () => {
    const user = userEvent.setup();

    render(
      <EntityEditModal
        open={true}
        onOpenChange={mockOnOpenChange}
        entity={mockEntity}
        onUpdated={mockOnUpdated}
      />
    );

    // Update the name
    const nameInput = screen.getByPlaceholderText(/Mail Carrier/i);
    await user.clear(nameInput);
    await user.type(nameInput, 'Jane Smith');

    const saveButton = screen.getByRole('button', { name: /Save/i });
    await user.click(saveButton);

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          entityId: 'entity-123',
          name: 'Jane Smith',
        })
      );
    });
  });

  it('handles mutation error gracefully', async () => {
    const user = userEvent.setup();
    const { toast } = await import('sonner');
    mockMutateAsync.mockRejectedValueOnce(new Error('Update failed'));

    render(
      <EntityEditModal
        open={true}
        onOpenChange={mockOnOpenChange}
        entity={mockEntity}
        onUpdated={mockOnUpdated}
      />
    );

    const saveButton = screen.getByRole('button', { name: /Save/i });
    await user.click(saveButton);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        'Failed to update entity',
        expect.objectContaining({ description: 'Update failed' })
      );
    });

    // Modal should not close on error
    expect(mockOnUpdated).not.toHaveBeenCalled();
  });

  it('renders without thumbnail when not provided', () => {
    const entityWithoutThumbnail: EntityEditData = {
      ...mockEntity,
      thumbnail_path: null,
    };

    render(
      <EntityEditModal
        open={true}
        onOpenChange={mockOnOpenChange}
        entity={entityWithoutThumbnail}
        onUpdated={mockOnUpdated}
      />
    );

    // Should not render an img element
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('handles null entity gracefully', () => {
    render(
      <EntityEditModal
        open={true}
        onOpenChange={mockOnOpenChange}
        entity={null}
        onUpdated={mockOnUpdated}
      />
    );

    // Modal should still render but with empty form
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});
