/**
 * EntityCardSkeleton component tests (Story P4-3.6)
 */

import React from 'react';
import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { EntityCardSkeleton } from '@/components/entities/EntityCardSkeleton';

describe('EntityCardSkeleton', () => {
  it('renders skeleton elements', () => {
    const { container } = render(<EntityCardSkeleton />);

    // Should render multiple skeleton elements
    const skeletonElements = container.querySelectorAll('[class*="animate-pulse"], [class*="bg-muted"]');
    expect(skeletonElements.length).toBeGreaterThan(0);
  });

  it('renders within a Card component', () => {
    const { container } = render(<EntityCardSkeleton />);

    // Card component renders a div with rounded-lg class
    const card = container.querySelector('[class*="rounded"]');
    expect(card).toBeInTheDocument();
  });
});
