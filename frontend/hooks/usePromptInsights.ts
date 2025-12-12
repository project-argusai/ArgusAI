/**
 * Story P4-5.4: Feedback-Informed Prompts
 *
 * Custom hooks for fetching prompt insights and applying suggestions
 * using TanStack Query.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import type {
  IPromptInsightsResponse,
  IApplySuggestionRequest,
  IApplySuggestionResponse,
  IABTestResultsResponse,
  IPromptHistoryResponse,
} from '@/types/event';

interface PromptInsightsParams {
  camera_id?: string;
}

interface ABTestResultsParams {
  start_date?: string;
  end_date?: string;
}

interface PromptHistoryParams {
  camera_id?: string;
  limit?: number;
}

/**
 * Hook for fetching prompt improvement suggestions
 *
 * @param params Optional filter: camera_id
 * @returns Query result with prompt insights data, loading state, and error
 *
 * @example
 * const { data, isLoading, error } = usePromptInsights({
 *   camera_id: 'abc123'
 * });
 */
export function usePromptInsights(params?: PromptInsightsParams) {
  return useQuery<IPromptInsightsResponse>({
    queryKey: ['prompt-insights', params?.camera_id],
    queryFn: () => apiClient.feedback.getPromptInsights(params),
    staleTime: 60 * 1000, // Consider data fresh for 1 minute
    refetchOnWindowFocus: false,
  });
}

/**
 * Hook for applying a prompt suggestion
 *
 * @returns Mutation for applying a suggestion
 *
 * @example
 * const { mutate: applySuggestion, isPending } = useApplySuggestion();
 * applySuggestion({ suggestion_id: 'sug_0' });
 */
export function useApplySuggestion() {
  const queryClient = useQueryClient();

  return useMutation<IApplySuggestionResponse, Error, IApplySuggestionRequest>({
    mutationFn: (data) => apiClient.feedback.applySuggestion(data),
    onSuccess: () => {
      // Invalidate related queries to refetch with updated data
      queryClient.invalidateQueries({ queryKey: ['prompt-insights'] });
      queryClient.invalidateQueries({ queryKey: ['prompt-history'] });
      queryClient.invalidateQueries({ queryKey: ['feedback-stats'] });
    },
  });
}

/**
 * Hook for fetching A/B test results
 *
 * @param params Optional date range filters
 * @returns Query result with A/B test statistics
 *
 * @example
 * const { data, isLoading } = useABTestResults({
 *   start_date: '2025-12-01',
 *   end_date: '2025-12-12'
 * });
 */
export function useABTestResults(params?: ABTestResultsParams) {
  return useQuery<IABTestResultsResponse>({
    queryKey: ['ab-test-results', params?.start_date, params?.end_date],
    queryFn: () => apiClient.feedback.getABTestResults(params),
    staleTime: 60 * 1000,
    refetchOnWindowFocus: false,
  });
}

/**
 * Hook for fetching prompt history
 *
 * @param params Optional filters: camera_id, limit
 * @returns Query result with prompt history entries
 *
 * @example
 * const { data, isLoading } = usePromptHistory({ limit: 10 });
 */
export function usePromptHistory(params?: PromptHistoryParams) {
  return useQuery<IPromptHistoryResponse>({
    queryKey: ['prompt-history', params?.camera_id, params?.limit],
    queryFn: () => apiClient.feedback.getPromptHistory(params),
    staleTime: 60 * 1000,
    refetchOnWindowFocus: false,
  });
}
