/**
 * UnsavedIndicator Component (Story P15-3.3)
 *
 * Visual indicator for unsaved changes in settings sections.
 * Shows an orange dot/badge that appears when isDirty is true.
 *
 * Usage:
 * <CardTitle className="flex items-center gap-2">
 *   Settings
 *   <UnsavedIndicator isDirty={isDirty} />
 * </CardTitle>
 */

'use client';

import { cn } from '@/lib/utils';

interface UnsavedIndicatorProps {
  /** Whether there are unsaved changes */
  isDirty: boolean;
  /** Optional className for additional styling */
  className?: string;
  /** Whether to show text label (default: false) */
  showLabel?: boolean;
  /** Size variant */
  size?: 'sm' | 'md';
}

/**
 * Visual indicator showing unsaved changes
 * Renders an orange dot with optional "Unsaved" label
 */
export function UnsavedIndicator({
  isDirty,
  className,
  showLabel = false,
  size = 'sm',
}: UnsavedIndicatorProps) {
  if (!isDirty) return null;

  const dotSize = size === 'sm' ? 'h-2 w-2' : 'h-2.5 w-2.5';

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 text-orange-500',
        className
      )}
      role="status"
      aria-label="Unsaved changes"
    >
      <span
        className={cn(
          dotSize,
          'rounded-full bg-orange-500 animate-pulse'
        )}
        aria-hidden="true"
      />
      {showLabel && (
        <span className="text-xs font-medium">Unsaved</span>
      )}
    </span>
  );
}

export default UnsavedIndicator;
