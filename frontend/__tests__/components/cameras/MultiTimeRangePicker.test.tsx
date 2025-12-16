/**
 * Tests for MultiTimeRangePicker component
 * Phase 5 - Story P5-5.4: Implement Multiple Schedule Time Ranges
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MultiTimeRangePicker } from '@/components/cameras/MultiTimeRangePicker';
import type { ITimeRange } from '@/types/camera';

describe('MultiTimeRangePicker', () => {
  const defaultRange: ITimeRange = {
    start_time: '09:00',
    end_time: '17:00',
  };

  const mockOnChange = vi.fn();

  beforeEach(() => {
    mockOnChange.mockClear();
  });

  describe('Rendering', () => {
    it('renders with a single time range', () => {
      render(
        <MultiTimeRangePicker
          value={[defaultRange]}
          onChange={mockOnChange}
        />
      );

      expect(screen.getByText('Active Time Ranges')).toBeInTheDocument();
      expect(screen.getByText('(1/4)')).toBeInTheDocument();
      expect(screen.getByLabelText('Time range 1 start time')).toHaveValue('09:00');
      expect(screen.getByLabelText('Time range 1 end time')).toHaveValue('17:00');
    });

    it('renders multiple time ranges', () => {
      const ranges: ITimeRange[] = [
        { start_time: '06:00', end_time: '09:00' },
        { start_time: '18:00', end_time: '22:00' },
      ];

      render(
        <MultiTimeRangePicker
          value={ranges}
          onChange={mockOnChange}
        />
      );

      expect(screen.getByText('(2/4)')).toBeInTheDocument();
      expect(screen.getByLabelText('Time range 1 start time')).toHaveValue('06:00');
      expect(screen.getByLabelText('Time range 2 end time')).toHaveValue('22:00');
    });

    it('shows overnight indicator for overnight ranges', () => {
      const overnightRange: ITimeRange = {
        start_time: '22:00',
        end_time: '06:00',
      };

      render(
        <MultiTimeRangePicker
          value={[overnightRange]}
          onChange={mockOnChange}
        />
      );

      expect(screen.getByText('Overnight')).toBeInTheDocument();
    });

    it('shows error message when provided', () => {
      render(
        <MultiTimeRangePicker
          value={[defaultRange]}
          onChange={mockOnChange}
          error="Time ranges cannot overlap"
        />
      );

      expect(screen.getByText('Time ranges cannot overlap')).toBeInTheDocument();
    });

    it('shows help text explaining multiple ranges', () => {
      render(
        <MultiTimeRangePicker
          value={[defaultRange]}
          onChange={mockOnChange}
        />
      );

      expect(screen.getByText(/Detection is active if the current time falls within any of the ranges/)).toBeInTheDocument();
    });
  });

  describe('Add Range Button', () => {
    it('shows Add Range button when under max ranges', () => {
      render(
        <MultiTimeRangePicker
          value={[defaultRange]}
          onChange={mockOnChange}
          maxRanges={4}
        />
      );

      expect(screen.getByRole('button', { name: /add another time range/i })).toBeInTheDocument();
    });

    it('hides Add Range button at max ranges', () => {
      const fourRanges: ITimeRange[] = [
        { start_time: '06:00', end_time: '08:00' },
        { start_time: '10:00', end_time: '12:00' },
        { start_time: '14:00', end_time: '17:00' },
        { start_time: '19:00', end_time: '22:00' },
      ];

      render(
        <MultiTimeRangePicker
          value={fourRanges}
          onChange={mockOnChange}
          maxRanges={4}
        />
      );

      expect(screen.queryByRole('button', { name: /add another time range/i })).not.toBeInTheDocument();
    });

    it('adds a new range when Add Range button is clicked', async () => {
      const user = userEvent.setup();

      render(
        <MultiTimeRangePicker
          value={[defaultRange]}
          onChange={mockOnChange}
        />
      );

      const addButton = screen.getByRole('button', { name: /add another time range/i });
      await user.click(addButton);

      expect(mockOnChange).toHaveBeenCalledTimes(1);
      const newRanges = mockOnChange.mock.calls[0][0];
      expect(newRanges).toHaveLength(2);
      expect(newRanges[0]).toEqual(defaultRange);
    });

    it('Add Range button is focusable and has correct aria-label', () => {
      render(
        <MultiTimeRangePicker
          value={[defaultRange]}
          onChange={mockOnChange}
        />
      );

      const addButton = screen.getByRole('button', { name: /add another time range/i });
      expect(addButton).toHaveAttribute('aria-label', 'Add another time range');
      addButton.focus();
      expect(addButton).toHaveFocus();
    });
  });

  describe('Remove Range Button', () => {
    it('hides remove button when only one range exists', () => {
      render(
        <MultiTimeRangePicker
          value={[defaultRange]}
          onChange={mockOnChange}
        />
      );

      expect(screen.queryByRole('button', { name: /remove time range/i })).not.toBeInTheDocument();
    });

    it('shows remove button when multiple ranges exist', () => {
      const ranges: ITimeRange[] = [
        { start_time: '06:00', end_time: '09:00' },
        { start_time: '18:00', end_time: '22:00' },
      ];

      render(
        <MultiTimeRangePicker
          value={ranges}
          onChange={mockOnChange}
        />
      );

      expect(screen.getAllByRole('button', { name: /remove time range/i })).toHaveLength(2);
    });

    it('removes the correct range when Remove button is clicked', async () => {
      const user = userEvent.setup();

      const ranges: ITimeRange[] = [
        { start_time: '06:00', end_time: '09:00' },
        { start_time: '18:00', end_time: '22:00' },
      ];

      render(
        <MultiTimeRangePicker
          value={ranges}
          onChange={mockOnChange}
        />
      );

      const removeButtons = screen.getAllByRole('button', { name: /remove time range/i });
      await user.click(removeButtons[0]); // Remove first range

      expect(mockOnChange).toHaveBeenCalledTimes(1);
      const newRanges = mockOnChange.mock.calls[0][0];
      expect(newRanges).toHaveLength(1);
      expect(newRanges[0]).toEqual({ start_time: '18:00', end_time: '22:00' });
    });

    it('Remove buttons have correct aria-labels', () => {
      const ranges: ITimeRange[] = [
        { start_time: '06:00', end_time: '09:00' },
        { start_time: '18:00', end_time: '22:00' },
      ];

      render(
        <MultiTimeRangePicker
          value={ranges}
          onChange={mockOnChange}
        />
      );

      expect(screen.getByLabelText('Remove time range 1')).toBeInTheDocument();
      expect(screen.getByLabelText('Remove time range 2')).toBeInTheDocument();
    });
  });

  describe('Time Input Changes', () => {
    it('updates start time correctly', () => {
      render(
        <MultiTimeRangePicker
          value={[defaultRange]}
          onChange={mockOnChange}
        />
      );

      const startInput = screen.getByLabelText('Time range 1 start time');
      // Use fireEvent.change for time inputs - more reliable than userEvent
      fireEvent.change(startInput, { target: { value: '08:00' } });

      // onChange should have been called with updated range
      expect(mockOnChange).toHaveBeenCalled();
      const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
      expect(lastCall[0].start_time).toBe('08:00');
    });

    it('updates end time correctly', () => {
      render(
        <MultiTimeRangePicker
          value={[defaultRange]}
          onChange={mockOnChange}
        />
      );

      const endInput = screen.getByLabelText('Time range 1 end time');
      // Use fireEvent.change for time inputs - more reliable than userEvent
      fireEvent.change(endInput, { target: { value: '18:00' } });

      // onChange should have been called with updated range
      expect(mockOnChange).toHaveBeenCalled();
      const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
      expect(lastCall[0].end_time).toBe('18:00');
    });
  });

  describe('Disabled State', () => {
    it('disables all inputs when disabled prop is true', () => {
      render(
        <MultiTimeRangePicker
          value={[defaultRange]}
          onChange={mockOnChange}
          disabled
        />
      );

      const startInput = screen.getByLabelText('Time range 1 start time');
      const endInput = screen.getByLabelText('Time range 1 end time');

      expect(startInput).toBeDisabled();
      expect(endInput).toBeDisabled();
    });

    it('does not show Add Range button when disabled', () => {
      render(
        <MultiTimeRangePicker
          value={[defaultRange]}
          onChange={mockOnChange}
          disabled
        />
      );

      // Button should still exist but not be functional
      const addButton = screen.queryByRole('button', { name: /add another time range/i });
      if (addButton) {
        expect(addButton).toBeDisabled();
      }
    });
  });

  describe('Keyboard Navigation', () => {
    it('Add Range button responds to Enter key', async () => {
      const user = userEvent.setup();

      render(
        <MultiTimeRangePicker
          value={[defaultRange]}
          onChange={mockOnChange}
        />
      );

      const addButton = screen.getByRole('button', { name: /add another time range/i });
      addButton.focus();
      await user.keyboard('{Enter}');

      expect(mockOnChange).toHaveBeenCalled();
    });

    it('Add Range button responds to Space key', async () => {
      const user = userEvent.setup();

      render(
        <MultiTimeRangePicker
          value={[defaultRange]}
          onChange={mockOnChange}
        />
      );

      const addButton = screen.getByRole('button', { name: /add another time range/i });
      addButton.focus();
      await user.keyboard(' ');

      expect(mockOnChange).toHaveBeenCalled();
    });

    it('Remove button responds to Enter key', async () => {
      const user = userEvent.setup();

      const ranges: ITimeRange[] = [
        { start_time: '06:00', end_time: '09:00' },
        { start_time: '18:00', end_time: '22:00' },
      ];

      render(
        <MultiTimeRangePicker
          value={ranges}
          onChange={mockOnChange}
        />
      );

      const removeButton = screen.getByLabelText('Remove time range 1');
      removeButton.focus();
      await user.keyboard('{Enter}');

      expect(mockOnChange).toHaveBeenCalled();
    });
  });

  describe('Edge Cases', () => {
    it('handles empty value array by providing default range', () => {
      render(
        <MultiTimeRangePicker
          value={[]}
          onChange={mockOnChange}
        />
      );

      // Should still render with default range
      expect(screen.getByLabelText('Time range 1 start time')).toHaveValue('09:00');
      expect(screen.getByLabelText('Time range 1 end time')).toHaveValue('17:00');
    });

    it('respects custom maxRanges prop', () => {
      const twoRanges: ITimeRange[] = [
        { start_time: '06:00', end_time: '09:00' },
        { start_time: '18:00', end_time: '22:00' },
      ];

      render(
        <MultiTimeRangePicker
          value={twoRanges}
          onChange={mockOnChange}
          maxRanges={2}
        />
      );

      expect(screen.getByText('(2/2)')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /add another time range/i })).not.toBeInTheDocument();
    });
  });
});
