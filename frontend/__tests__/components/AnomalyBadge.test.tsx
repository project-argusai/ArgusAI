/**
 * Tests for Story P4-7.3: AnomalyBadge component
 *
 * Tests visual badge rendering for different anomaly severity levels:
 * - No badge for low anomaly (< 0.3)
 * - Yellow "Unusual" badge for medium anomaly (0.3 - 0.6)
 * - Red "Anomaly" badge for high anomaly (> 0.6)
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AnomalyBadge, getAnomalySeverity } from '@/components/events/AnomalyBadge';

describe('AnomalyBadge', () => {
  describe('getAnomalySeverity', () => {
    it('returns null for null score', () => {
      expect(getAnomalySeverity(null)).toBeNull();
    });

    it('returns null for undefined score', () => {
      expect(getAnomalySeverity(undefined)).toBeNull();
    });

    it('returns "low" for scores below 0.3', () => {
      expect(getAnomalySeverity(0)).toBe('low');
      expect(getAnomalySeverity(0.1)).toBe('low');
      expect(getAnomalySeverity(0.25)).toBe('low');
      expect(getAnomalySeverity(0.29)).toBe('low');
    });

    it('returns "medium" for scores between 0.3 and 0.6', () => {
      expect(getAnomalySeverity(0.3)).toBe('medium');
      expect(getAnomalySeverity(0.45)).toBe('medium');
      expect(getAnomalySeverity(0.59)).toBe('medium');
    });

    it('returns "high" for scores 0.6 and above', () => {
      expect(getAnomalySeverity(0.6)).toBe('high');
      expect(getAnomalySeverity(0.75)).toBe('high');
      expect(getAnomalySeverity(0.9)).toBe('high');
      expect(getAnomalySeverity(1.0)).toBe('high');
    });
  });

  describe('rendering', () => {
    it('renders nothing for null score', () => {
      const { container } = render(<AnomalyBadge score={null} />);
      expect(container.firstChild).toBeNull();
    });

    it('renders nothing for undefined score', () => {
      const { container } = render(<AnomalyBadge score={undefined} />);
      expect(container.firstChild).toBeNull();
    });

    it('renders nothing for low anomaly score (0.2)', () => {
      const { container } = render(<AnomalyBadge score={0.2} />);
      expect(container.firstChild).toBeNull();
    });

    it('renders "Unusual" badge for medium anomaly (0.45)', () => {
      render(<AnomalyBadge score={0.45} />);

      const badge = screen.getByTestId('anomaly-badge');
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent('Unusual');
      expect(badge).toHaveAttribute('data-severity', 'medium');
    });

    it('renders "Anomaly" badge for high anomaly (0.75)', () => {
      render(<AnomalyBadge score={0.75} />);

      const badge = screen.getByTestId('anomaly-badge');
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent('Anomaly');
      expect(badge).toHaveAttribute('data-severity', 'high');
    });

    it('renders badge at exact medium threshold (0.3)', () => {
      render(<AnomalyBadge score={0.3} />);

      const badge = screen.getByTestId('anomaly-badge');
      expect(badge).toHaveTextContent('Unusual');
      expect(badge).toHaveAttribute('data-severity', 'medium');
    });

    it('renders badge at exact high threshold (0.6)', () => {
      render(<AnomalyBadge score={0.6} />);

      const badge = screen.getByTestId('anomaly-badge');
      expect(badge).toHaveTextContent('Anomaly');
      expect(badge).toHaveAttribute('data-severity', 'high');
    });
  });

  describe('styling', () => {
    it('has amber/yellow styling for medium anomaly', () => {
      render(<AnomalyBadge score={0.45} />);

      const badge = screen.getByTestId('anomaly-badge');
      expect(badge.className).toContain('bg-amber');
      expect(badge.className).toContain('text-amber');
    });

    it('has red styling for high anomaly', () => {
      render(<AnomalyBadge score={0.75} />);

      const badge = screen.getByTestId('anomaly-badge');
      expect(badge.className).toContain('bg-red');
      expect(badge.className).toContain('text-red');
    });
  });

  describe('tooltip', () => {
    it('shows tooltip by default', () => {
      render(<AnomalyBadge score={0.72} />);

      // The tooltip trigger should be present
      const badge = screen.getByTestId('anomaly-badge');
      expect(badge).toBeInTheDocument();
    });

    it('can hide tooltip when showTooltip is false', () => {
      render(<AnomalyBadge score={0.72} showTooltip={false} />);

      // Badge should still render
      const badge = screen.getByTestId('anomaly-badge');
      expect(badge).toBeInTheDocument();
    });
  });

  describe('custom className', () => {
    it('accepts additional className', () => {
      render(<AnomalyBadge score={0.75} className="custom-class" />);

      const badge = screen.getByTestId('anomaly-badge');
      expect(badge.className).toContain('custom-class');
    });
  });
});
