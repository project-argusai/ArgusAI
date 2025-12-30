/**
 * FrameSamplingStrategySelector Component Tests
 * Story P8-2.5: Add Frame Sampling Strategy Selection in Settings
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FrameSamplingStrategySelector } from '@/components/settings/FrameSamplingStrategySelector';

describe('FrameSamplingStrategySelector', () => {
  const mockOnChange = vi.fn();

  beforeEach(() => {
    mockOnChange.mockClear();
  });

  describe('Rendering (AC5.1, AC5.2)', () => {
    it('renders all three strategy options', () => {
      render(
        <FrameSamplingStrategySelector
          value="uniform"
          onChange={mockOnChange}
        />
      );

      expect(screen.getByText('Uniform')).toBeInTheDocument();
      expect(screen.getByText('Adaptive')).toBeInTheDocument();
      expect(screen.getByText('Hybrid')).toBeInTheDocument();
    });

    it('renders the label "Frame Sampling Strategy"', () => {
      render(
        <FrameSamplingStrategySelector
          value="uniform"
          onChange={mockOnChange}
        />
      );

      expect(screen.getByText('Frame Sampling Strategy')).toBeInTheDocument();
    });

    it('renders radio buttons for each option', () => {
      render(
        <FrameSamplingStrategySelector
          value="uniform"
          onChange={mockOnChange}
        />
      );

      // Should have 3 radio buttons
      const radioButtons = screen.getAllByRole('radio');
      expect(radioButtons).toHaveLength(3);
    });
  });

  describe('Option Descriptions (AC5.3)', () => {
    it('shows description for Uniform option', () => {
      render(
        <FrameSamplingStrategySelector
          value="uniform"
          onChange={mockOnChange}
        />
      );

      expect(screen.getByText(/Fixed interval extraction/i)).toBeInTheDocument();
      expect(screen.getByText(/Best for static cameras/i)).toBeInTheDocument();
    });

    it('shows description for Adaptive option', () => {
      render(
        <FrameSamplingStrategySelector
          value="uniform"
          onChange={mockOnChange}
        />
      );

      expect(screen.getByText(/Content-aware selection/i)).toBeInTheDocument();
      expect(screen.getByText(/Best for busy areas/i)).toBeInTheDocument();
    });

    it('shows description for Hybrid option', () => {
      render(
        <FrameSamplingStrategySelector
          value="uniform"
          onChange={mockOnChange}
        />
      );

      expect(screen.getByText(/Extracts extra candidates then filters/i)).toBeInTheDocument();
      expect(screen.getByText(/Best for varied content/i)).toBeInTheDocument();
    });
  });

  describe('Selection State', () => {
    it('marks uniform as selected when value is uniform', () => {
      render(
        <FrameSamplingStrategySelector
          value="uniform"
          onChange={mockOnChange}
        />
      );

      // Use id to find the specific radio button
      const uniformRadio = document.getElementById('strategy-uniform');
      expect(uniformRadio).toHaveAttribute('data-state', 'checked');
    });

    it('marks adaptive as selected when value is adaptive', () => {
      render(
        <FrameSamplingStrategySelector
          value="adaptive"
          onChange={mockOnChange}
        />
      );

      const adaptiveRadio = document.getElementById('strategy-adaptive');
      expect(adaptiveRadio).toHaveAttribute('data-state', 'checked');
    });

    it('marks hybrid as selected when value is hybrid', () => {
      render(
        <FrameSamplingStrategySelector
          value="hybrid"
          onChange={mockOnChange}
        />
      );

      const hybridRadio = document.getElementById('strategy-hybrid');
      expect(hybridRadio).toHaveAttribute('data-state', 'checked');
    });
  });

  describe('Selection Change', () => {
    it('calls onChange with "adaptive" when adaptive is selected', () => {
      render(
        <FrameSamplingStrategySelector
          value="uniform"
          onChange={mockOnChange}
        />
      );

      const adaptiveRadio = document.getElementById('strategy-adaptive');
      fireEvent.click(adaptiveRadio!);

      expect(mockOnChange).toHaveBeenCalledWith('adaptive');
    });

    it('calls onChange with "hybrid" when hybrid is selected', () => {
      render(
        <FrameSamplingStrategySelector
          value="uniform"
          onChange={mockOnChange}
        />
      );

      const hybridRadio = document.getElementById('strategy-hybrid');
      fireEvent.click(hybridRadio!);

      expect(mockOnChange).toHaveBeenCalledWith('hybrid');
    });

    it('calls onChange with "uniform" when uniform is selected', () => {
      render(
        <FrameSamplingStrategySelector
          value="adaptive"
          onChange={mockOnChange}
        />
      );

      const uniformRadio = document.getElementById('strategy-uniform');
      fireEvent.click(uniformRadio!);

      expect(mockOnChange).toHaveBeenCalledWith('uniform');
    });
  });

  describe('Disabled State', () => {
    it('disables all radio buttons when disabled prop is true', () => {
      render(
        <FrameSamplingStrategySelector
          value="uniform"
          onChange={mockOnChange}
          disabled={true}
        />
      );

      const radioButtons = screen.getAllByRole('radio');
      radioButtons.forEach(radio => {
        expect(radio).toBeDisabled();
      });
    });

    it('does not call onChange when disabled and clicked', () => {
      render(
        <FrameSamplingStrategySelector
          value="uniform"
          onChange={mockOnChange}
          disabled={true}
        />
      );

      const adaptiveRadio = document.getElementById('strategy-adaptive');
      fireEvent.click(adaptiveRadio!);

      expect(mockOnChange).not.toHaveBeenCalled();
    });
  });

  describe('Helper Text', () => {
    it('shows help text about frame selection', () => {
      render(
        <FrameSamplingStrategySelector
          value="uniform"
          onChange={mockOnChange}
        />
      );

      expect(screen.getByText(/Controls how frames are selected/i)).toBeInTheDocument();
    });
  });
});
