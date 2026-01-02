/**
 * ReclassifyingIndicator component tests
 * Story P16-4.3: Tests for re-classification loading indicator
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ReclassifyingIndicator } from '@/components/events/ReclassifyingIndicator';

describe('ReclassifyingIndicator', () => {
  // AC1: Shows loading indicator with "Re-classifying..." text when active
  it('renders loading indicator when isActive is true', () => {
    render(<ReclassifyingIndicator isActive={true} />);

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText('Re-classifying...')).toBeInTheDocument();
  });

  it('renders spinner icon when active', () => {
    render(<ReclassifyingIndicator isActive={true} />);

    const statusElement = screen.getByRole('status');
    expect(statusElement.querySelector('svg')).toBeInTheDocument();
  });

  it('does not render when isActive is false', () => {
    render(<ReclassifyingIndicator isActive={false} />);

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByText('Re-classifying...')).not.toBeInTheDocument();
  });

  it('has accessible aria-label', () => {
    render(<ReclassifyingIndicator isActive={true} />);

    expect(screen.getByLabelText('Re-classifying event')).toBeInTheDocument();
  });

  it('uses aria-live for screen reader announcements', () => {
    render(<ReclassifyingIndicator isActive={true} />);

    const statusElement = screen.getByRole('status');
    expect(statusElement).toHaveAttribute('aria-live', 'polite');
  });

  it('applies custom className when provided', () => {
    render(<ReclassifyingIndicator isActive={true} className="custom-class" />);

    const statusElement = screen.getByRole('status');
    expect(statusElement).toHaveClass('custom-class');
  });

  it('has amber/warning styling', () => {
    render(<ReclassifyingIndicator isActive={true} />);

    const statusElement = screen.getByRole('status');
    expect(statusElement).toHaveClass('bg-amber-100');
    expect(statusElement).toHaveClass('text-amber-700');
  });
});
