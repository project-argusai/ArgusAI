/**
 * Story P9-3.4: Summary Feedback Buttons
 *
 * Custom hooks for managing summary feedback using TanStack Query mutations.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient, ApiError } from '@/lib/api-client';
import type { ISummaryFeedback } from '@/types/event';

interface SubmitSummaryFeedbackParams {
  summaryId: string;
  rating: 'positive' | 'negative';
  correctionText?: string;
}

interface SummaryFeedbackResponse {
  id: string;
  summary_id: string;
  rating: 'positive' | 'negative';
  correction_text: string | null;
  created_at: string;
  updated_at: string | null;
}

/**
 * Hook for fetching feedback for a summary
 *
 * @example
 * const { data: feedback, isLoading } = useSummaryFeedback('123');
 */
export function useSummaryFeedback(summaryId: string) {
  return useQuery<ISummaryFeedback | null, ApiError>({
    queryKey: ['summaryFeedback', summaryId],
    queryFn: async () => {
      try {
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/summaries/${summaryId}/feedback`
        );
        if (response.status === 404) {
          return null;
        }
        if (!response.ok) {
          throw new Error('Failed to fetch summary feedback');
        }
        return response.json();
      } catch {
        return null;
      }
    },
    enabled: !!summaryId,
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
}

/**
 * Hook for submitting feedback on a summary
 *
 * @example
 * const { mutate: submitFeedback, isPending } = useSubmitSummaryFeedback();
 * submitFeedback({ summaryId: '123', rating: 'positive' });
 */
export function useSubmitSummaryFeedback() {
  const queryClient = useQueryClient();

  return useMutation<SummaryFeedbackResponse, ApiError, SubmitSummaryFeedbackParams>({
    mutationFn: async ({ summaryId, rating, correctionText }) => {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/summaries/${summaryId}/feedback`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            rating,
            correction_text: correctionText ?? null,
          }),
        }
      );
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Failed to submit feedback' }));
        throw new Error(error.detail || 'Failed to submit feedback');
      }
      return response.json();
    },
    onSuccess: (_data, variables) => {
      // Invalidate feedback query to refresh data
      queryClient.invalidateQueries({ queryKey: ['summaryFeedback', variables.summaryId] });
      queryClient.invalidateQueries({ queryKey: ['summaries'] });
    },
  });
}

/**
 * Hook for updating existing feedback on a summary
 *
 * @example
 * const { mutate: updateFeedback, isPending } = useUpdateSummaryFeedback();
 * updateFeedback({ summaryId: '123', rating: 'negative', correctionText: 'Missed an event' });
 */
export function useUpdateSummaryFeedback() {
  const queryClient = useQueryClient();

  return useMutation<SummaryFeedbackResponse, ApiError, SubmitSummaryFeedbackParams>({
    mutationFn: async ({ summaryId, rating, correctionText }) => {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/summaries/${summaryId}/feedback`,
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            rating,
            correction_text: correctionText ?? null,
          }),
        }
      );
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Failed to update feedback' }));
        throw new Error(error.detail || 'Failed to update feedback');
      }
      return response.json();
    },
    onSuccess: (_data, variables) => {
      // Invalidate feedback query to refresh data
      queryClient.invalidateQueries({ queryKey: ['summaryFeedback', variables.summaryId] });
      queryClient.invalidateQueries({ queryKey: ['summaries'] });
    },
  });
}

/**
 * Hook for deleting feedback from a summary
 *
 * @example
 * const { mutate: deleteFeedback, isPending } = useDeleteSummaryFeedback();
 * deleteFeedback('123');
 */
export function useDeleteSummaryFeedback() {
  const queryClient = useQueryClient();

  return useMutation<void, ApiError, string>({
    mutationFn: async (summaryId) => {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/summaries/${summaryId}/feedback`,
        {
          method: 'DELETE',
        }
      );
      if (!response.ok && response.status !== 204) {
        const error = await response.json().catch(() => ({ detail: 'Failed to delete feedback' }));
        throw new Error(error.detail || 'Failed to delete feedback');
      }
    },
    onSuccess: (_, summaryId) => {
      // Invalidate feedback query to refresh data
      queryClient.invalidateQueries({ queryKey: ['summaryFeedback', summaryId] });
      queryClient.invalidateQueries({ queryKey: ['summaries'] });
    },
  });
}
