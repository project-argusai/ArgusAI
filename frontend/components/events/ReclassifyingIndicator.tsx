/**
 * ReclassifyingIndicator - Shows loading state during entity assignment re-classification
 *
 * Story P16-4.3: Display Re-classification Status
 * AC1: Shows loading indicator with "Re-classifying..." text when active
 */

'use client';

import { Loader2 } from 'lucide-react';

interface ReclassifyingIndicatorProps {
  /** Whether re-classification is in progress */
  isActive: boolean;
  /** Optional custom class name */
  className?: string;
}

/**
 * ReclassifyingIndicator Component
 *
 * Displays a loading indicator when an event is being re-classified
 * after entity assignment.
 */
export function ReclassifyingIndicator({
  isActive,
  className = '',
}: ReclassifyingIndicatorProps) {
  if (!isActive) {
    return null;
  }

  return (
    <div
      className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-700 ${className}`}
      role="status"
      aria-live="polite"
      aria-label="Re-classifying event"
    >
      <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
      <span>Re-classifying...</span>
    </div>
  );
}
