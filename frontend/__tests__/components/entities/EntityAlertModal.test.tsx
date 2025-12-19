/**
 * EntityAlertModal component tests (Story P7-4.3)
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { EntityAlertModal } from '@/components/entities/EntityAlertModal';
import type { IEntity } from '@/types/entity';

// Mock sonner toast
vi.mock('sonner', () => ({
  toast: {
    info: vi.fn(),
  },
}));

// Mock next/link
vi.mock('next/link', () => ({
  default: ({ children, href, onClick, ...props }: { children: React.ReactNode; href: string; onClick?: () => void }) => (
    <a href={href} onClick={onClick} {...props}>{children}</a>
  ),
}));

describe('EntityAlertModal', () => {
  const mockEntity: IEntity = {
    id: 'entity-123',
    entity_type: 'person',
    name: 'John Doe',
    first_seen_at: '2024-01-15T10:30:00Z',
    last_seen_at: '2024-06-20T14:45:00Z',
    occurrence_count: 15,
  };

  const mockOnClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  // AC1: Modal opens from entity card
  it('renders when isOpen is true (Story P7-4.3 AC1)', () => {
    render(
      <EntityAlertModal
        isOpen={true}
        onClose={mockOnClose}
        entity={mockEntity}
      />
    );

    expect(screen.getByText(/Create Alert for John Doe/)).toBeInTheDocument();
  });

  it('does not render when isOpen is false', () => {
    render(
      <EntityAlertModal
        isOpen={false}
        onClose={mockOnClose}
        entity={mockEntity}
      />
    );

    expect(screen.queryByText(/Create Alert for John Doe/)).not.toBeInTheDocument();
  });

  // AC2: Shows "Notify when seen" option
  it('displays "Notify when seen" toggle (Story P7-4.3 AC2)', () => {
    render(
      <EntityAlertModal
        isOpen={true}
        onClose={mockOnClose}
        entity={mockEntity}
      />
    );

    expect(screen.getByText('Notify when seen')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: /notify when seen/i })).toBeInTheDocument();
  });

  // AC3: Shows "Notify when NOT seen for X hours" option
  it('displays "Notify when NOT seen" toggle with hour input (Story P7-4.3 AC3)', () => {
    render(
      <EntityAlertModal
        isOpen={true}
        onClose={mockOnClose}
        entity={mockEntity}
      />
    );

    expect(screen.getByText('Notify when NOT seen')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: /notify when not seen/i })).toBeInTheDocument();
  });

  it('shows hour input when "Notify when NOT seen" is enabled', async () => {
    render(
      <EntityAlertModal
        isOpen={true}
        onClose={mockOnClose}
        entity={mockEntity}
      />
    );

    // Enable the "Notify when NOT seen" switch
    const notSeenSwitch = screen.getByRole('switch', { name: /notify when not seen/i });
    fireEvent.click(notSeenSwitch);

    // Hour input should now be visible
    await waitFor(() => {
      expect(screen.getByRole('spinbutton', { name: /hours until not seen alert/i })).toBeInTheDocument();
    });
    expect(screen.getByText(/hours without detection/)).toBeInTheDocument();
  });

  // AC4: Time range configuration displayed
  it('displays time range configuration options (Story P7-4.3 AC4)', () => {
    render(
      <EntityAlertModal
        isOpen={true}
        onClose={mockOnClose}
        entity={mockEntity}
      />
    );

    expect(screen.getByText('Alert Schedule')).toBeInTheDocument();
    expect(screen.getByLabelText('All day (24/7)')).toBeInTheDocument();
    expect(screen.getByLabelText('Custom schedule')).toBeInTheDocument();
  });

  it('shows custom schedule message when Custom is selected', async () => {
    render(
      <EntityAlertModal
        isOpen={true}
        onClose={mockOnClose}
        entity={mockEntity}
      />
    );

    // Click on "Custom schedule" radio
    const customRadio = screen.getByLabelText('Custom schedule');
    fireEvent.click(customRadio);

    // Should show the coming soon message for custom scheduling
    await waitFor(() => {
      expect(screen.getByText(/Custom scheduling options will be available/)).toBeInTheDocument();
    });
  });

  // AC5: "Coming Soon" message shown when save attempted
  it('shows "Coming Soon" toast when Save is clicked (Story P7-4.3 AC5)', async () => {
    const { toast } = await import('sonner');

    render(
      <EntityAlertModal
        isOpen={true}
        onClose={mockOnClose}
        entity={mockEntity}
      />
    );

    const saveButton = screen.getByRole('button', { name: /save alert/i });
    fireEvent.click(saveButton);

    expect(toast.info).toHaveBeenCalledWith('Coming Soon', {
      description: expect.stringContaining('Entity-based alerts will be available'),
    });
    expect(mockOnClose).toHaveBeenCalled();
  });

  // AC6: Link to alert rules page provided
  it('displays link to alert rules page (Story P7-4.3 AC6)', () => {
    render(
      <EntityAlertModal
        isOpen={true}
        onClose={mockOnClose}
        entity={mockEntity}
      />
    );

    const rulesLink = screen.getByRole('link', { name: /view alert rules/i });
    expect(rulesLink).toBeInTheDocument();
    expect(rulesLink).toHaveAttribute('href', '/rules');
  });

  it('closes modal when Cancel is clicked', () => {
    render(
      <EntityAlertModal
        isOpen={true}
        onClose={mockOnClose}
        entity={mockEntity}
      />
    );

    const cancelButton = screen.getByRole('button', { name: /cancel/i });
    fireEvent.click(cancelButton);

    expect(mockOnClose).toHaveBeenCalled();
  });

  it('handles entity with null name', () => {
    const unnamedEntity: IEntity = {
      ...mockEntity,
      name: null,
    };

    render(
      <EntityAlertModal
        isOpen={true}
        onClose={mockOnClose}
        entity={unnamedEntity}
      />
    );

    expect(screen.getByText(/Create Alert for Unknown person/)).toBeInTheDocument();
  });

  it('handles vehicle entity type', () => {
    const vehicleEntity: IEntity = {
      ...mockEntity,
      entity_type: 'vehicle',
      name: 'Blue Sedan',
    };

    render(
      <EntityAlertModal
        isOpen={true}
        onClose={mockOnClose}
        entity={vehicleEntity}
      />
    );

    expect(screen.getByText(/Create Alert for Blue Sedan/)).toBeInTheDocument();
    expect(screen.getByText(/Configure when you want to be notified about this vehicle/)).toBeInTheDocument();
  });
});
