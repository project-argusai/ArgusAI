/**
 * Story P4-5.4: Feedback-Informed Prompts
 *
 * Displays AI prompt improvement suggestions based on user feedback analysis.
 * Allows admin to apply or dismiss suggestions to improve AI description accuracy.
 */

'use client';

import { useState } from 'react';
import { usePromptInsights, useApplySuggestion } from '@/hooks/usePromptInsights';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Lightbulb, Check, X, ChevronDown, ChevronUp, AlertTriangle, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import type { IPromptSuggestion, CorrectionCategory } from '@/types/event';

/**
 * Maps correction categories to human-readable labels
 */
const CATEGORY_LABELS: Record<CorrectionCategory, string> = {
  object_misidentification: 'Object Misidentification',
  action_wrong: 'Incorrect Action',
  missing_detail: 'Missing Detail',
  context_error: 'Context Error',
  general: 'General',
};

/**
 * Maps correction categories to colors
 */
const CATEGORY_COLORS: Record<CorrectionCategory, string> = {
  object_misidentification: 'bg-red-100 text-red-800 border-red-200',
  action_wrong: 'bg-orange-100 text-orange-800 border-orange-200',
  missing_detail: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  context_error: 'bg-blue-100 text-blue-800 border-blue-200',
  general: 'bg-gray-100 text-gray-800 border-gray-200',
};

interface SuggestionCardProps {
  suggestion: IPromptSuggestion;
  onApply: () => void;
  onDismiss: () => void;
  isApplying: boolean;
}

function SuggestionCard({ suggestion, onApply, onDismiss, isApplying }: SuggestionCardProps) {
  const [showExamples, setShowExamples] = useState(false);

  return (
    <Card className="border-l-4 border-l-primary">
      <CardContent className="pt-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-2">
              <Badge variant="outline" className={CATEGORY_COLORS[suggestion.category]}>
                {CATEGORY_LABELS[suggestion.category]}
              </Badge>
              <span className="text-sm text-muted-foreground">
                Impact: {Math.round(suggestion.impact_score * 100)}%
              </span>
              <span className="text-sm text-muted-foreground">
                Confidence: {Math.round(suggestion.confidence * 100)}%
              </span>
            </div>

            <p className="text-sm mb-3">{suggestion.suggestion_text}</p>

            {suggestion.example_corrections.length > 0 && (
              <div>
                <button
                  onClick={() => setShowExamples(!showExamples)}
                  className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
                  aria-expanded={showExamples}
                >
                  {showExamples ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  {suggestion.example_corrections.length} example correction{suggestion.example_corrections.length !== 1 ? 's' : ''}
                </button>

                {showExamples && (
                  <ul className="mt-2 space-y-1 text-sm text-muted-foreground bg-muted/50 rounded p-2">
                    {suggestion.example_corrections.map((example, index) => (
                      <li key={index} className="italic">&ldquo;{example}&rdquo;</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={onDismiss}
              disabled={isApplying}
              title="Dismiss suggestion"
            >
              <X className="h-4 w-4" />
            </Button>
            <Button
              size="sm"
              onClick={onApply}
              disabled={isApplying}
              title="Apply suggestion to prompt"
            >
              {isApplying ? (
                <span className="animate-spin mr-1">...</span>
              ) : (
                <Check className="h-4 w-4 mr-1" />
              )}
              Apply
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

interface PromptInsightsProps {
  cameraId?: string;
}

export function PromptInsights({ cameraId }: PromptInsightsProps) {
  const { data, isLoading, error, refetch } = usePromptInsights(
    cameraId ? { camera_id: cameraId } : undefined
  );
  const applySuggestion = useApplySuggestion();
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());

  const handleApply = async (suggestion: IPromptSuggestion) => {
    try {
      const result = await applySuggestion.mutateAsync({
        suggestion_id: suggestion.id,
        camera_id: suggestion.camera_id ?? cameraId,
      });

      toast.success(`Suggestion applied! ${result.message}`);
      refetch();
    } catch (err) {
      toast.error('Failed to apply suggestion');
      console.error('Apply suggestion error:', err);
    }
  };

  const handleDismiss = (id: string) => {
    setDismissedIds(prev => new Set([...prev, id]));
    toast.info('Suggestion dismissed');
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Lightbulb className="h-5 w-5" />
            Prompt Improvement Suggestions
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <div className="animate-pulse text-muted-foreground">Loading insights...</div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Lightbulb className="h-5 w-5" />
            Prompt Improvement Suggestions
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-destructive">Failed to load prompt insights</div>
        </CardContent>
      </Card>
    );
  }

  // Filter out dismissed suggestions
  const activeSuggestions = data?.suggestions.filter(
    s => !dismissedIds.has(s.id)
  ) ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-yellow-500" />
          Prompt Improvement Suggestions
        </CardTitle>
        <CardDescription>
          Based on analysis of {data?.sample_count ?? 0} feedback corrections
          {data?.confidence ? ` (${Math.round(data.confidence * 100)}% confidence)` : ''}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {!data?.min_samples_met ? (
          <div className="flex items-start gap-3 p-4 bg-muted rounded-lg">
            <AlertTriangle className="h-5 w-5 text-yellow-600 mt-0.5" />
            <div>
              <p className="font-medium">Insufficient Data</p>
              <p className="text-sm text-muted-foreground">
                Need at least 10 feedback corrections with text to generate suggestions.
                Currently have {data?.sample_count ?? 0} samples.
              </p>
            </div>
          </div>
        ) : activeSuggestions.length === 0 ? (
          <div className="flex items-center justify-center py-8 text-muted-foreground">
            <div className="text-center">
              <Lightbulb className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p>No suggestions available</p>
              <p className="text-sm">AI descriptions are performing well based on current feedback</p>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {activeSuggestions.map(suggestion => (
              <SuggestionCard
                key={suggestion.id}
                suggestion={suggestion}
                onApply={() => handleApply(suggestion)}
                onDismiss={() => handleDismiss(suggestion.id)}
                isApplying={applySuggestion.isPending}
              />
            ))}
          </div>
        )}

        {/* Camera-specific insights summary */}
        {data && Object.keys(data.camera_insights).length > 0 && (
          <div className="mt-6 pt-6 border-t">
            <h4 className="font-medium mb-3">Camera-Specific Insights</h4>
            <div className="space-y-2">
              {Object.values(data.camera_insights).map(insight => (
                <div
                  key={insight.camera_id}
                  className="flex items-center justify-between p-3 bg-muted/50 rounded"
                >
                  <div>
                    <span className="font-medium">{insight.camera_name}</span>
                    <span className="text-sm text-muted-foreground ml-2">
                      ({insight.sample_count} corrections)
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`text-sm ${insight.accuracy_rate >= 70 ? 'text-green-600' : 'text-red-600'}`}>
                      {insight.accuracy_rate.toFixed(1)}% accuracy
                    </span>
                    {insight.suggestions.length > 0 && (
                      <Badge variant="secondary">
                        {insight.suggestions.length} suggestion{insight.suggestions.length !== 1 ? 's' : ''}
                      </Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
