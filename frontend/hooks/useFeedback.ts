/**
 * Story P4-5.1: Feedback Collection UI
 *
 * Custom hooks for managing event feedback using TanStack Query mutations.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient, ApiError } from '@/lib/api-client';
import type { IEvent } from '@/types/event';

interface SubmitFeedbackParams {
  eventId: string;
  rating: 'helpful' | 'not_helpful';
  correction?: string;
}

/**
 * Hook for submitting feedback on an event
 *
 * @example
 * const { mutate: submitFeedback, isPending } = useSubmitFeedback();
 * submitFeedback({ eventId: '123', rating: 'helpful' });
 */
export function useSubmitFeedback() {
  const queryClient = useQueryClient();

  return useMutation<IEvent, ApiError, SubmitFeedbackParams>({
    mutationFn: async ({ eventId, rating, correction }) => {
      const feedback = { rating, correction: correction ?? null };
      return apiClient.events.submitFeedback(eventId, feedback);
    },
    onSuccess: (_data, variables) => {
      // Invalidate event queries to refresh feedback data
      queryClient.invalidateQueries({ queryKey: ['events'] });
      queryClient.invalidateQueries({ queryKey: ['event', variables.eventId] });
    },
  });
}

/**
 * Hook for updating existing feedback on an event
 * Note: Uses the same submitFeedback endpoint as updates overwrite existing feedback
 *
 * @example
 * const { mutate: updateFeedback, isPending } = useUpdateFeedback();
 * updateFeedback({ eventId: '123', rating: 'not_helpful', correction: 'Wrong description' });
 */
export function useUpdateFeedback() {
  const queryClient = useQueryClient();

  return useMutation<IEvent, ApiError, SubmitFeedbackParams>({
    mutationFn: async ({ eventId, rating, correction }) => {
      const feedback = { rating, correction: correction ?? null };
      return apiClient.events.submitFeedback(eventId, feedback);
    },
    onSuccess: (_data, variables) => {
      // Invalidate event queries to refresh feedback data
      queryClient.invalidateQueries({ queryKey: ['events'] });
      queryClient.invalidateQueries({ queryKey: ['event', variables.eventId] });
    },
  });
}

/**
 * Hook for deleting feedback from an event
 * Note: Deletes by submitting with no feedback (reset)
 *
 * @example
 * const { mutate: deleteFeedback, isPending } = useDeleteFeedback();
 * deleteFeedback('123');
 */
export function useDeleteFeedback() {
  const queryClient = useQueryClient();

  return useMutation<IEvent, ApiError, string>({
    mutationFn: async (eventId) => {
      // Delete feedback by submitting empty feedback
      return apiClient.events.submitFeedback(eventId, { rating: 'helpful' });
    },
    onSuccess: (_, eventId) => {
      // Invalidate event queries to refresh feedback data
      queryClient.invalidateQueries({ queryKey: ['events'] });
      queryClient.invalidateQueries({ queryKey: ['event', eventId] });
    },
  });
}
