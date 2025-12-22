/**
 * Story P9-3.4: Summary Feedback Buttons
 *
 * SummaryFeedbackButtons component - allows users to provide quick feedback on AI summaries
 * using thumbs up/down buttons with optional correction text input.
 */

'use client';

import { useState, memo, useCallback } from 'react';
import { ThumbsUp, ThumbsDown, Loader2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import {
  useSummaryFeedback,
  useSubmitSummaryFeedback,
  useUpdateSummaryFeedback,
} from '@/hooks/useSummaryFeedback';
import type { ISummaryFeedback } from '@/types/event';
import { cn } from '@/lib/utils';

interface SummaryFeedbackButtonsProps {
  /** Summary UUID to submit feedback for */
  summaryId: string;
  /** Existing feedback if any (for showing selected state) */
  existingFeedback?: ISummaryFeedback | null;
  /** Callback when feedback changes */
  onFeedbackChange?: (feedback: ISummaryFeedback) => void;
  /** Additional class names */
  className?: string;
}

const CORRECTION_MAX_LENGTH = 500;

export const SummaryFeedbackButtons = memo(function SummaryFeedbackButtons({
  summaryId,
  existingFeedback,
  onFeedbackChange,
  className,
}: SummaryFeedbackButtonsProps) {
  const [showCorrection, setShowCorrection] = useState(false);
  const [correctionText, setCorrectionText] = useState('');
  const [localFeedback, setLocalFeedback] = useState<ISummaryFeedback | null>(existingFeedback ?? null);

  // Fetch existing feedback if not provided
  const { data: fetchedFeedback } = useSummaryFeedback(summaryId);
  const currentFeedback = localFeedback ?? fetchedFeedback ?? existingFeedback;

  const { mutate: submitFeedback, isPending: isSubmitting } = useSubmitSummaryFeedback();
  const { mutate: updateFeedback, isPending: isUpdating } = useUpdateSummaryFeedback();

  const isPending = isSubmitting || isUpdating;

  // Get current rating
  const currentRating = currentFeedback?.rating;

  const handleFeedback = useCallback((
    rating: 'positive' | 'negative',
    correctionTextValue?: string
  ) => {
    const mutationFn = currentRating ? updateFeedback : submitFeedback;

    mutationFn(
      {
        summaryId,
        rating,
        correctionText: correctionTextValue || undefined,
      },
      {
        onSuccess: (data) => {
          const feedback: ISummaryFeedback = {
            id: data.id,
            summary_id: data.summary_id,
            rating: data.rating,
            correction_text: data.correction_text,
            created_at: data.created_at,
            updated_at: data.updated_at,
          };
          setLocalFeedback(feedback);
          onFeedbackChange?.(feedback);
          setShowCorrection(false);
          setCorrectionText('');
          toast.success('Thanks for the feedback!', {
            description: rating === 'positive' ? 'Glad the summary was helpful!' : 'Your feedback helps improve accuracy.',
          });
        },
        onError: (error) => {
          toast.error('Failed to submit feedback', {
            description: error.message || 'Please try again.',
          });
        },
      }
    );
  }, [summaryId, currentRating, submitFeedback, updateFeedback, onFeedbackChange]);

  const handleThumbsUp = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (isPending) return;
    handleFeedback('positive');
  }, [handleFeedback, isPending]);

  const handleThumbsDown = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (isPending) return;
    setShowCorrection(true);
  }, [isPending]);

  const handleSubmitCorrection = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (isPending) return;
    handleFeedback('negative', correctionText);
  }, [handleFeedback, correctionText, isPending]);

  const handleSkipCorrection = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (isPending) return;
    handleFeedback('negative');
  }, [handleFeedback, isPending]);

  const handleCancelCorrection = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setShowCorrection(false);
    setCorrectionText('');
  }, []);

  const handleCorrectionChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    if (value.length <= CORRECTION_MAX_LENGTH) {
      setCorrectionText(value);
    }
  }, []);

  // Prevent clicks from bubbling
  const handleContainerClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
  }, []);

  return (
    <div className={cn("flex flex-col gap-2", className)} onClick={handleContainerClick}>
      <div className="flex items-center gap-1">
        {/* Thumbs Up Button */}
        <Button
          variant={currentRating === 'positive' ? 'default' : 'ghost'}
          size="sm"
          onClick={handleThumbsUp}
          disabled={isPending}
          aria-label={currentRating === 'positive' ? 'Marked as helpful' : 'Mark as helpful'}
          aria-pressed={currentRating === 'positive'}
          className={cn(
            "h-8 w-8 p-0",
            currentRating === 'positive' && "bg-green-600 hover:bg-green-700 text-white"
          )}
        >
          {isPending && !showCorrection ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <ThumbsUp className={cn(
              "h-4 w-4",
              currentRating === 'positive' && "fill-current"
            )} />
          )}
        </Button>

        {/* Thumbs Down Button */}
        <Button
          variant={currentRating === 'negative' ? 'default' : 'ghost'}
          size="sm"
          onClick={handleThumbsDown}
          disabled={isPending}
          aria-label={currentRating === 'negative' ? 'Marked as not helpful' : 'Mark as not helpful'}
          aria-pressed={currentRating === 'negative'}
          className={cn(
            "h-8 w-8 p-0",
            currentRating === 'negative' && "bg-red-600 hover:bg-red-700 text-white"
          )}
        >
          <ThumbsDown className={cn(
            "h-4 w-4",
            currentRating === 'negative' && "fill-current"
          )} />
        </Button>
      </div>

      {/* Correction Input (shows on thumbs down) - AC-3.4.4 */}
      {showCorrection && (
        <div className="flex flex-col gap-2 p-3 bg-muted rounded-lg border animate-in fade-in slide-in-from-top-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">What was missing? (optional)</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleCancelCorrection}
              className="h-6 w-6 p-0"
              aria-label="Cancel correction"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
          <Textarea
            value={correctionText}
            onChange={handleCorrectionChange}
            placeholder="Describe what the summary missed or got wrong..."
            className="min-h-[80px] text-sm resize-none"
            maxLength={CORRECTION_MAX_LENGTH}
            aria-label="Correction text"
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              {correctionText.length}/{CORRECTION_MAX_LENGTH}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleSkipCorrection}
                disabled={isPending}
              >
                Skip
              </Button>
              <Button
                size="sm"
                onClick={handleSubmitCorrection}
                disabled={isPending}
              >
                {isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Submitting...
                  </>
                ) : (
                  'Submit'
                )}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
});
