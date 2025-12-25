/**
 * Story P4-5.1: Feedback Collection UI
 * Story P9-3.3: Package False Positive Feedback
 * Story P10-4.3: Allow Feedback Modification - Added proper update/delete hooks
 *
 * Custom hooks for managing event feedback using TanStack Query mutations.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient, ApiError } from '@/lib/api-client';
import type { IEvent, IEventFeedback } from '@/types/event';

interface SubmitFeedbackParams {
  eventId: string;
  rating: 'helpful' | 'not_helpful';
  correction?: string;
  correction_type?: 'not_package';  // Story P9-3.3: Correction type
}

interface UpdateFeedbackParams {
  eventId: string;
  rating?: 'helpful' | 'not_helpful';
  correction?: string | null;
  correction_type?: 'not_package' | null;
}

/**
 * Hook for submitting feedback on an event (creates new feedback)
 *
 * @example
 * const { mutate: submitFeedback, isPending } = useSubmitFeedback();
 * submitFeedback({ eventId: '123', rating: 'helpful' });
 */
export function useSubmitFeedback() {
  const queryClient = useQueryClient();

  return useMutation<IEvent, ApiError, SubmitFeedbackParams>({
    mutationFn: async ({ eventId, rating, correction, correction_type }) => {
      const feedback = {
        rating,
        correction: correction ?? null,
        correction_type: correction_type ?? null,  // Story P9-3.3
      };
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
 * Hook for updating existing feedback on an event (Story P10-4.3)
 * Uses PUT endpoint to modify existing feedback
 *
 * @example
 * const { mutate: updateFeedback, isPending } = useUpdateFeedback();
 * updateFeedback({ eventId: '123', rating: 'not_helpful', correction: 'Wrong description' });
 */
export function useUpdateFeedback() {
  const queryClient = useQueryClient();

  return useMutation<IEventFeedback, ApiError, UpdateFeedbackParams>({
    mutationFn: async ({ eventId, rating, correction, correction_type }) => {
      const feedback: {
        rating?: 'helpful' | 'not_helpful';
        correction?: string | null;
        correction_type?: 'not_package' | null;
      } = {};

      if (rating !== undefined) feedback.rating = rating;
      if (correction !== undefined) feedback.correction = correction;
      if (correction_type !== undefined) feedback.correction_type = correction_type;

      return apiClient.events.updateFeedback(eventId, feedback);
    },
    onSuccess: (_data, variables) => {
      // Invalidate event queries to refresh feedback data
      queryClient.invalidateQueries({ queryKey: ['events'] });
      queryClient.invalidateQueries({ queryKey: ['event', variables.eventId] });
    },
  });
}

/**
 * Hook for deleting feedback from an event (Story P10-4.3)
 * Uses DELETE endpoint to remove feedback entirely
 *
 * @example
 * const { mutate: deleteFeedback, isPending } = useDeleteFeedback();
 * deleteFeedback('123'); // eventId
 */
export function useDeleteFeedback() {
  const queryClient = useQueryClient();

  return useMutation<void, ApiError, string>({
    mutationFn: async (eventId) => {
      await apiClient.events.deleteFeedback(eventId);
    },
    onSuccess: (_, eventId) => {
      // Invalidate event queries to refresh feedback data
      queryClient.invalidateQueries({ queryKey: ['events'] });
      queryClient.invalidateQueries({ queryKey: ['event', eventId] });
    },
  });
}
