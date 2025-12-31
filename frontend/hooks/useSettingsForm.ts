/**
 * useSettingsForm Hook (Story P15-3.2)
 *
 * A generic hook for managing settings form state with:
 * - Dirty detection (deep comparison)
 * - Save/reset actions
 * - Loading state
 * - Error handling
 * - TanStack Query integration
 *
 * Usage:
 * const { formData, updateField, isDirty, save, reset, isSaving } = useSettingsForm(
 *   initialData,
 *   saveFn,
 *   queryKey
 * );
 */

'use client';

import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

/**
 * Return type for useSettingsForm hook
 */
export interface UseSettingsFormReturn<T> {
  /** Current form data */
  formData: T;
  /** Update entire form data */
  setFormData: React.Dispatch<React.SetStateAction<T>>;
  /** Update a single field */
  updateField: <K extends keyof T>(field: K, value: T[K]) => void;
  /** Whether form has unsaved changes */
  isDirty: boolean;
  /** Save current form data */
  save: () => Promise<void>;
  /** Reset form to initial values */
  reset: () => void;
  /** Whether save is in progress */
  isSaving: boolean;
  /** Whether data is loading */
  isLoading: boolean;
  /** Error from last save attempt */
  error: Error | null;
  /** Clear error */
  clearError: () => void;
}

/**
 * Options for useSettingsForm
 */
export interface UseSettingsFormOptions<T> {
  /** Initial data for the form */
  initialData: T;
  /** Function to call when saving (returns promise) */
  saveFn: (data: T) => Promise<unknown>;
  /** Query key to invalidate on save (optional) */
  queryKey?: string[];
  /** Success message for toast (optional, default: "Settings saved") */
  successMessage?: string;
  /** Whether data is still loading */
  isLoading?: boolean;
  /** Called after successful save */
  onSuccess?: (data: T) => void;
  /** Called on save error */
  onError?: (error: Error) => void;
}

/**
 * Deep equality comparison for objects
 * Handles nested objects, arrays, and primitives
 */
function deepEqual<T>(a: T, b: T): boolean {
  if (a === b) return true;

  if (typeof a !== typeof b) return false;
  if (a === null || b === null) return a === b;
  if (typeof a !== 'object') return a === b;

  // Handle arrays
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return false;
    return a.every((item, index) => deepEqual(item, b[index]));
  }

  // Handle objects
  if (Array.isArray(a) !== Array.isArray(b)) return false;

  const keysA = Object.keys(a as object);
  const keysB = Object.keys(b as object);

  if (keysA.length !== keysB.length) return false;

  return keysA.every((key) =>
    deepEqual(
      (a as Record<string, unknown>)[key],
      (b as Record<string, unknown>)[key]
    )
  );
}

/**
 * Deep clone an object
 */
function deepClone<T>(obj: T): T {
  if (obj === null || typeof obj !== 'object') return obj;
  if (Array.isArray(obj)) return obj.map(deepClone) as T;
  return Object.fromEntries(
    Object.entries(obj as object).map(([k, v]) => [k, deepClone(v)])
  ) as T;
}

/**
 * Generic settings form state management hook
 *
 * @example
 * const { formData, updateField, isDirty, save, reset, isSaving } = useSettingsForm({
 *   initialData: settings,
 *   saveFn: (data) => apiClient.settings.update(data),
 *   queryKey: ['settings'],
 *   successMessage: 'Settings saved successfully',
 * });
 */
export function useSettingsForm<T extends object>({
  initialData,
  saveFn,
  queryKey,
  successMessage = 'Settings saved',
  isLoading = false,
  onSuccess,
  onError,
}: UseSettingsFormOptions<T>): UseSettingsFormReturn<T> {
  const queryClient = useQueryClient();

  // Store deep clone of initial data for comparison
  const initialRef = useRef<T>(deepClone(initialData));

  // Form state
  const [formData, setFormData] = useState<T>(() => deepClone(initialData));
  const [error, setError] = useState<Error | null>(null);

  // Update initial ref and form data when initialData changes (e.g., from query)
  useEffect(() => {
    if (!isLoading) {
      initialRef.current = deepClone(initialData);
      setFormData(deepClone(initialData));
    }
  }, [initialData, isLoading]);

  // Compute isDirty with deep comparison
  const isDirty = useMemo(
    () => !deepEqual(formData, initialRef.current),
    [formData]
  );

  // Update a single field
  const updateField = useCallback(<K extends keyof T>(field: K, value: T[K]) => {
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
  }, []);

  // Reset form to initial values
  const reset = useCallback(() => {
    setFormData(deepClone(initialRef.current));
    setError(null);
  }, []);

  // Clear error
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Save mutation
  const mutation = useMutation({
    mutationFn: (data: T) => saveFn(data),
    onSuccess: (_result, data) => {
      // Update initial ref to current data (it's now saved)
      initialRef.current = deepClone(data);
      setError(null);
      toast.success(successMessage);

      // Invalidate related queries
      if (queryKey) {
        queryClient.invalidateQueries({ queryKey });
      }

      onSuccess?.(data);
    },
    onError: (err: Error) => {
      setError(err);
      toast.error('Failed to save settings', {
        description: err.message,
      });
      onError?.(err);
    },
  });

  // Save function
  const save = useCallback(async () => {
    await mutation.mutateAsync(formData);
  }, [mutation, formData]);

  return {
    formData,
    setFormData,
    updateField,
    isDirty,
    save,
    reset,
    isSaving: mutation.isPending,
    isLoading,
    error,
    clearError,
  };
}

export default useSettingsForm;
