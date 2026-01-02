/**
 * EntityAssignConfirmDialog component tests
 * Story P16-4.1: Tests for entity assignment confirmation dialog
 * Story P16-4.2: Tests for "Don't show again" preference
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { EntityAssignConfirmDialog, SKIP_ENTITY_ASSIGN_WARNING_KEY } from '@/components/entities/EntityAssignConfirmDialog';

describe('EntityAssignConfirmDialog', () => {
  const mockOnOpenChange = vi.fn();
  const mockOnConfirm = vi.fn();
  const mockOnCancel = vi.fn();

  const defaultProps = {
    open: true,
    onOpenChange: mockOnOpenChange,
    entityName: 'John Doe',
    onConfirm: mockOnConfirm,
    onCancel: mockOnCancel,
    isLoading: false,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  // AC1: Confirmation dialog appears before assignment
  it('renders dialog when open is true', () => {
    render(<EntityAssignConfirmDialog {...defaultProps} />);

    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(screen.getByText('Confirm Entity Assignment')).toBeInTheDocument();
  });

  // AC2: Shows entity name in message
  it('displays entity name in the message', () => {
    render(<EntityAssignConfirmDialog {...defaultProps} entityName="Jane Smith" />);

    expect(screen.getByText(/Jane Smith/)).toBeInTheDocument();
    expect(screen.getByText(/will trigger AI re-classification/)).toBeInTheDocument();
  });

  // AC3: Shows re-classification info message
  it('displays re-classification information', () => {
    render(<EntityAssignConfirmDialog {...defaultProps} />);

    expect(
      screen.getByText(/will update the event description based on the entity context/)
    ).toBeInTheDocument();
  });

  // AC4: Shows estimated API cost
  it('displays estimated API cost', () => {
    render(<EntityAssignConfirmDialog {...defaultProps} />);

    expect(screen.getByText(/Estimated API cost:/)).toBeInTheDocument();
    expect(screen.getByText(/~\$0\.002/)).toBeInTheDocument();
  });

  it('displays custom estimated cost when provided', () => {
    render(<EntityAssignConfirmDialog {...defaultProps} estimatedCost="~$0.005" />);

    expect(screen.getByText(/~\$0\.005/)).toBeInTheDocument();
  });

  // AC5: Confirm triggers assignment
  it('calls onConfirm when Confirm button is clicked', () => {
    render(<EntityAssignConfirmDialog {...defaultProps} />);

    const confirmButton = screen.getByRole('button', { name: 'Confirm' });
    fireEvent.click(confirmButton);

    expect(mockOnConfirm).toHaveBeenCalledTimes(1);
  });

  // AC6: Cancel returns to entity selection
  it('calls onCancel and closes dialog when Cancel button is clicked', () => {
    render(<EntityAssignConfirmDialog {...defaultProps} />);

    const cancelButton = screen.getByRole('button', { name: 'Cancel' });
    fireEvent.click(cancelButton);

    expect(mockOnCancel).toHaveBeenCalledTimes(1);
    expect(mockOnOpenChange).toHaveBeenCalledWith(false);
  });

  it('shows loading state when isLoading is true', () => {
    render(<EntityAssignConfirmDialog {...defaultProps} isLoading={true} />);

    expect(screen.getByRole('button', { name: 'Assigning...' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Assigning...' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  });

  it('does not render dialog when open is false', () => {
    render(<EntityAssignConfirmDialog {...defaultProps} open={false} />);

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('displays warning icon in dialog header', () => {
    render(<EntityAssignConfirmDialog {...defaultProps} />);

    // The AlertTriangle icon should be present (it has an SVG class)
    const dialogHeader = screen.getByText('Confirm Entity Assignment').parentElement;
    expect(dialogHeader?.querySelector('svg')).toBeInTheDocument();
  });

  // Story P16-4.2: "Don't show again" checkbox tests
  describe('Don\'t show again checkbox (P16-4.2)', () => {
    let localStorageMock: { [key: string]: string };

    beforeEach(() => {
      // Mock localStorage for testing
      localStorageMock = {};
      vi.stubGlobal('localStorage', {
        getItem: vi.fn((key: string) => localStorageMock[key] || null),
        setItem: vi.fn((key: string, value: string) => {
          localStorageMock[key] = value;
        }),
        removeItem: vi.fn((key: string) => {
          delete localStorageMock[key];
        }),
        clear: vi.fn(() => {
          localStorageMock = {};
        }),
      });
    });

    afterEach(() => {
      vi.unstubAllGlobals();
    });

    // AC1: Checkbox renders and can be checked
    it('renders "Don\'t show this warning again" checkbox', () => {
      render(<EntityAssignConfirmDialog {...defaultProps} />);

      expect(screen.getByRole('checkbox', { name: /don't show this warning again/i })).toBeInTheDocument();
      expect(screen.getByText(/Don't show this warning again/i)).toBeInTheDocument();
    });

    it('checkbox is unchecked by default', () => {
      render(<EntityAssignConfirmDialog {...defaultProps} />);

      const checkbox = screen.getByRole('checkbox', { name: /don't show this warning again/i });
      expect(checkbox).not.toBeChecked();
    });

    it('checkbox can be checked', () => {
      render(<EntityAssignConfirmDialog {...defaultProps} />);

      const checkbox = screen.getByRole('checkbox', { name: /don't show this warning again/i });
      fireEvent.click(checkbox);

      expect(checkbox).toBeChecked();
    });

    // AC2: Save preference to localStorage on confirm with checkbox checked
    it('saves preference to localStorage when confirm clicked with checkbox checked', () => {
      render(<EntityAssignConfirmDialog {...defaultProps} />);

      const checkbox = screen.getByRole('checkbox', { name: /don't show this warning again/i });
      fireEvent.click(checkbox);

      const confirmButton = screen.getByRole('button', { name: 'Confirm' });
      fireEvent.click(confirmButton);

      expect(localStorage.setItem).toHaveBeenCalledWith(SKIP_ENTITY_ASSIGN_WARNING_KEY, 'true');
      expect(localStorageMock[SKIP_ENTITY_ASSIGN_WARNING_KEY]).toBe('true');
    });

    it('does not save preference to localStorage when confirm clicked without checkbox', () => {
      render(<EntityAssignConfirmDialog {...defaultProps} />);

      const confirmButton = screen.getByRole('button', { name: 'Confirm' });
      fireEvent.click(confirmButton);

      expect(localStorage.setItem).not.toHaveBeenCalled();
      expect(localStorageMock[SKIP_ENTITY_ASSIGN_WARNING_KEY]).toBeUndefined();
    });

    // AC4: Preference key constant is exported correctly
    it('exports the correct localStorage key constant', () => {
      expect(SKIP_ENTITY_ASSIGN_WARNING_KEY).toBe('argusai_skip_entity_assign_warning');
    });

    it('checkbox resets when cancel is clicked', () => {
      render(<EntityAssignConfirmDialog {...defaultProps} />);

      // Check the checkbox
      const checkbox = screen.getByRole('checkbox', { name: /don't show this warning again/i });
      fireEvent.click(checkbox);
      expect(checkbox).toBeChecked();

      // Click cancel
      const cancelButton = screen.getByRole('button', { name: 'Cancel' });
      fireEvent.click(cancelButton);

      // Checkbox state should be reset (dialog closes, but state resets)
      expect(mockOnCancel).toHaveBeenCalled();
      // localStorage should not have been set since cancel was clicked
      expect(localStorage.setItem).not.toHaveBeenCalled();
    });
  });
});
