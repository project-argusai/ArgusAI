/**
 * useUnsavedChangesWarning Hook (Story P15-3.4)
 *
 * Warns users before navigating away with unsaved changes.
 * Handles both browser navigation (beforeunload) and SPA navigation.
 *
 * Usage:
 * useUnsavedChangesWarning(isDirty, 'You have unsaved changes');
 */

'use client';

import { useEffect, useCallback } from 'react';

/**
 * Options for useUnsavedChangesWarning
 */
interface UseUnsavedChangesWarningOptions {
  /** Whether there are unsaved changes */
  isDirty: boolean;
  /** Warning message (optional, default: "You have unsaved changes") */
  message?: string;
  /** Whether to enable the warning (default: true) */
  enabled?: boolean;
}

/**
 * Hook that warns users before leaving the page with unsaved changes
 *
 * Features:
 * - Browser beforeunload event for refresh/close
 * - Blocks accidental navigation
 *
 * @example
 * useUnsavedChangesWarning({ isDirty });
 */
export function useUnsavedChangesWarning({
  isDirty,
  message = 'You have unsaved changes. Are you sure you want to leave?',
  enabled = true,
}: UseUnsavedChangesWarningOptions): void {
  // Handle beforeunload (browser navigation)
  const handleBeforeUnload = useCallback(
    (e: BeforeUnloadEvent) => {
      if (!enabled || !isDirty) return;

      // Standard way to trigger browser warning
      e.preventDefault();
      // Some browsers require returnValue to be set
      e.returnValue = message;
      return message;
    },
    [isDirty, message, enabled]
  );

  useEffect(() => {
    if (!enabled) return;

    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [handleBeforeUnload, enabled]);
}

/**
 * Simplified version - just pass isDirty boolean
 *
 * @example
 * useUnsavedChangesWarning({ isDirty: form.isDirty });
 */
export default useUnsavedChangesWarning;
