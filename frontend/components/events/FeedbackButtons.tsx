/**
 * Story P4-5.1: Feedback Collection UI
 * Story P9-3.3: Package False Positive Feedback
 * Story P10-4.3: Allow Feedback Modification
 *
 * FeedbackButtons component - allows users to provide quick feedback on AI event descriptions
 * using thumbs up/down buttons with optional correction text input.
 * For package detections, includes a "Not a package" button.
 * Story P10-4.3: Added ability to modify/remove feedback after initial submission.
 */

'use client';

import { useState, memo, useCallback, useMemo } from 'react';
import { ThumbsUp, ThumbsDown, Loader2, X, Package, Pencil, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { toast } from 'sonner';
import { useSubmitFeedback, useUpdateFeedback, useDeleteFeedback } from '@/hooks/useFeedback';
import type { IEventFeedback } from '@/types/event';
import { cn } from '@/lib/utils';

interface FeedbackButtonsProps {
  /** Event UUID to submit feedback for */
  eventId: string;
  /** Existing feedback if any (for showing selected state) */
  existingFeedback?: IEventFeedback | null;
  /** Callback when feedback changes */
  onFeedbackChange?: (feedback: IEventFeedback | null) => void;
  /** Additional class names */
  className?: string;
  /** Story P9-3.3: Smart detection type for showing correction buttons */
  smartDetectionType?: string | null;
}

const CORRECTION_MAX_LENGTH = 500;

export const FeedbackButtons = memo(function FeedbackButtons({
  eventId,
  existingFeedback,
  onFeedbackChange,
  className,
  smartDetectionType,
}: FeedbackButtonsProps) {
  const [showCorrection, setShowCorrection] = useState(false);
  const [correction, setCorrection] = useState('');
  const [localFeedback, setLocalFeedback] = useState<IEventFeedback | null>(existingFeedback ?? null);
  // Story P10-4.3: State for edit mode
  const [editingCorrection, setEditingCorrection] = useState(false);
  const [editCorrection, setEditCorrection] = useState('');
  const [showRemoveConfirm, setShowRemoveConfirm] = useState(false);
  const [activePopover, setActivePopover] = useState<'up' | 'down' | null>(null);

  const { mutate: submitFeedback, isPending: isSubmitting } = useSubmitFeedback();
  const { mutate: updateFeedback, isPending: isUpdating } = useUpdateFeedback();
  const { mutate: deleteFeedback, isPending: isDeleting } = useDeleteFeedback();

  const isPending = isSubmitting || isUpdating || isDeleting;

  // Get current rating (from local state or prop)
  const currentRating = localFeedback?.rating ?? existingFeedback?.rating;
  // Story P9-3.3: Get current correction type
  const currentCorrectionType = localFeedback?.correction_type ?? existingFeedback?.correction_type;
  const currentCorrection = localFeedback?.correction ?? existingFeedback?.correction;
  const isPackageEvent = smartDetectionType === 'package';
  const isMarkedNotPackage = currentCorrectionType === 'not_package';
  // Story P10-4.3: Check if feedback was edited
  const wasEdited = localFeedback?.was_edited ?? existingFeedback?.was_edited ?? false;
  const updatedAt = localFeedback?.updated_at ?? existingFeedback?.updated_at;

  // Format the edited timestamp for tooltip
  const editedTooltip = useMemo(() => {
    if (!wasEdited || !updatedAt) return null;
    try {
      const date = new Date(updatedAt);
      return `Edited on ${date.toLocaleDateString()} at ${date.toLocaleTimeString()}`;
    } catch {
      return 'Edited';
    }
  }, [wasEdited, updatedAt]);

  // Story P10-4.3: Handle changing rating
  const handleChangeRating = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (isPending || !currentRating) return;

    const newRating = currentRating === 'helpful' ? 'not_helpful' : 'helpful';

    updateFeedback(
      { eventId, rating: newRating },
      {
        onSuccess: (data) => {
          setLocalFeedback(data);
          onFeedbackChange?.(data);
          setActivePopover(null);
          toast.success('Feedback updated', {
            description: `Changed to ${newRating === 'helpful' ? 'thumbs up' : 'thumbs down'}`,
          });
        },
        onError: (error) => {
          toast.error('Failed to update feedback', {
            description: error.message || 'Please try again.',
          });
        },
      }
    );
  }, [eventId, currentRating, updateFeedback, onFeedbackChange, isPending]);

  // Story P10-4.3: Handle editing correction
  const handleStartEditCorrection = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setEditCorrection(currentCorrection || '');
    setEditingCorrection(true);
    setActivePopover(null);
  }, [currentCorrection]);

  const handleSaveEditCorrection = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (isPending) return;

    updateFeedback(
      { eventId, correction: editCorrection || null },
      {
        onSuccess: (data) => {
          setLocalFeedback(data);
          onFeedbackChange?.(data);
          setEditingCorrection(false);
          setEditCorrection('');
          toast.success('Correction updated');
        },
        onError: (error) => {
          toast.error('Failed to update correction', {
            description: error.message || 'Please try again.',
          });
        },
      }
    );
  }, [eventId, editCorrection, updateFeedback, onFeedbackChange, isPending]);

  const handleCancelEditCorrection = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingCorrection(false);
    setEditCorrection('');
  }, []);

  // Story P10-4.3: Handle removing feedback
  const handleRemoveFeedback = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setActivePopover(null);
    setShowRemoveConfirm(true);
  }, []);

  const handleConfirmRemove = useCallback(() => {
    if (isPending) return;

    deleteFeedback(eventId, {
      onSuccess: () => {
        setLocalFeedback(null);
        onFeedbackChange?.(null);
        setShowRemoveConfirm(false);
        toast.success('Feedback removed');
      },
      onError: (error) => {
        toast.error('Failed to remove feedback', {
          description: error.message || 'Please try again.',
        });
      },
    });
  }, [eventId, deleteFeedback, onFeedbackChange, isPending]);

  // Original handlers for new feedback
  const handleFeedback = useCallback((
    rating: 'helpful' | 'not_helpful',
    correctionText?: string,
    correctionType?: 'not_package'
  ) => {
    // If feedback already exists, use update; otherwise use submit
    const mutationFn = currentRating ? updateFeedback : submitFeedback;
    const params = currentRating
      ? { eventId, rating, correction: correctionText || undefined, correction_type: correctionType }
      : { eventId, rating, correction: correctionText, correction_type: correctionType };

    mutationFn(
      params,
      {
        onSuccess: (data) => {
          // Handle both IEvent (from submit) and IEventFeedback (from update) responses
          const feedback = 'feedback' in data ? data.feedback : data;
          if (feedback) {
            setLocalFeedback(feedback as IEventFeedback);
            onFeedbackChange?.(feedback as IEventFeedback);
          }
          setShowCorrection(false);
          setCorrection('');
          // Story P9-3.3: Different toast for package false positive
          if (correctionType === 'not_package') {
            toast.success('Feedback recorded', {
              description: 'Thanks! This helps improve package detection accuracy.',
            });
          } else {
            toast.success('Feedback submitted', {
              description: rating === 'helpful' ? 'Thanks for the feedback!' : 'Thanks! Your correction helps improve accuracy.',
            });
          }
        },
        onError: (error) => {
          toast.error('Failed to submit feedback', {
            description: error.message || 'Please try again.',
          });
        },
      }
    );
  }, [eventId, currentRating, submitFeedback, updateFeedback, onFeedbackChange]);

  const handleThumbsUp = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (isPending) return;

    // Story P10-4.3: If already thumbs up, show options
    if (currentRating === 'helpful') {
      setActivePopover('up');
      return;
    }

    handleFeedback('helpful');
  }, [handleFeedback, isPending, currentRating]);

  const handleThumbsDown = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (isPending) return;

    // Story P10-4.3: If already thumbs down, show options
    if (currentRating === 'not_helpful') {
      setActivePopover('down');
      return;
    }

    setShowCorrection(true);
  }, [isPending, currentRating]);

  // Story P9-3.3: Handle "Not a package" click
  const handleNotPackage = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (isPending || isMarkedNotPackage) return;
    handleFeedback('not_helpful', undefined, 'not_package');
  }, [handleFeedback, isPending, isMarkedNotPackage]);

  const handleSubmitCorrection = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (isPending) return;
    handleFeedback('not_helpful', correction);
  }, [handleFeedback, correction, isPending]);

  const handleSkipCorrection = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (isPending) return;
    handleFeedback('not_helpful');
  }, [handleFeedback, isPending]);

  const handleCancelCorrection = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setShowCorrection(false);
    setCorrection('');
  }, []);

  const handleCorrectionChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    if (value.length <= CORRECTION_MAX_LENGTH) {
      setCorrection(value);
    }
  }, []);

  const handleEditCorrectionChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    if (value.length <= CORRECTION_MAX_LENGTH) {
      setEditCorrection(value);
    }
  }, []);

  // Prevent clicks from bubbling to EventCard
  const handleContainerClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
  }, []);

  // Options menu content for active feedback buttons
  const renderOptionsMenu = (isThumbsUp: boolean) => (
    <div className="flex flex-col gap-1 py-1">
      <Button
        variant="ghost"
        size="sm"
        className="justify-start gap-2 text-xs"
        onClick={handleChangeRating}
        disabled={isPending}
      >
        {isThumbsUp ? <ThumbsDown className="h-3 w-3" /> : <ThumbsUp className="h-3 w-3" />}
        Change to {isThumbsUp ? 'thumbs down' : 'thumbs up'}
      </Button>

      {!isThumbsUp && (
        <Button
          variant="ghost"
          size="sm"
          className="justify-start gap-2 text-xs"
          onClick={handleStartEditCorrection}
          disabled={isPending}
        >
          <Pencil className="h-3 w-3" />
          {currentCorrection ? 'Edit correction' : 'Add correction'}
        </Button>
      )}

      <Button
        variant="ghost"
        size="sm"
        className="justify-start gap-2 text-xs text-destructive hover:text-destructive"
        onClick={handleRemoveFeedback}
        disabled={isPending}
      >
        <Trash2 className="h-3 w-3" />
        Remove feedback
      </Button>
    </div>
  );

  return (
    <TooltipProvider>
      <div className={cn("flex flex-col gap-2", className)} onClick={handleContainerClick}>
        <div className="flex items-center gap-1">
          {/* Thumbs Up Button */}
          <Popover open={activePopover === 'up'} onOpenChange={(open) => setActivePopover(open ? 'up' : null)}>
            <PopoverTrigger asChild>
              <Button
                variant={currentRating === 'helpful' ? 'default' : 'ghost'}
                size="sm"
                onClick={handleThumbsUp}
                disabled={isPending}
                aria-label={currentRating === 'helpful' ? 'Marked as helpful - click to modify' : 'Mark as helpful'}
                aria-pressed={currentRating === 'helpful'}
                className={cn(
                  "h-8 w-8 p-0",
                  currentRating === 'helpful' && "bg-green-600 hover:bg-green-700 text-white"
                )}
              >
                {isPending && !showCorrection && !editingCorrection ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <ThumbsUp className={cn(
                    "h-4 w-4",
                    currentRating === 'helpful' && "fill-current"
                  )} />
                )}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-48 p-1" align="start">
              {renderOptionsMenu(true)}
            </PopoverContent>
          </Popover>

          {/* Thumbs Down Button */}
          <Popover open={activePopover === 'down'} onOpenChange={(open) => setActivePopover(open ? 'down' : null)}>
            <PopoverTrigger asChild>
              <Button
                variant={currentRating === 'not_helpful' ? 'default' : 'ghost'}
                size="sm"
                onClick={handleThumbsDown}
                disabled={isPending}
                aria-label={currentRating === 'not_helpful' ? 'Marked as not helpful - click to modify' : 'Mark as not helpful'}
                aria-pressed={currentRating === 'not_helpful'}
                className={cn(
                  "h-8 w-8 p-0",
                  currentRating === 'not_helpful' && "bg-red-600 hover:bg-red-700 text-white"
                )}
              >
                <ThumbsDown className={cn(
                  "h-4 w-4",
                  currentRating === 'not_helpful' && "fill-current"
                )} />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-48 p-1" align="start">
              {renderOptionsMenu(false)}
            </PopoverContent>
          </Popover>

          {/* Story P9-3.3: "Not a package" Button for package events */}
          {isPackageEvent && (
            <Button
              variant={isMarkedNotPackage ? 'default' : 'outline'}
              size="sm"
              onClick={handleNotPackage}
              disabled={isPending || isMarkedNotPackage}
              aria-label={isMarkedNotPackage ? 'Marked as not a package' : 'Not a package'}
              aria-pressed={isMarkedNotPackage}
              className={cn(
                "h-8 px-2 text-xs gap-1",
                isMarkedNotPackage && "bg-orange-600 hover:bg-orange-600 text-white cursor-default"
              )}
            >
              <Package className="h-3 w-3" />
              <X className="h-3 w-3 -ml-1" />
              {isMarkedNotPackage ? 'Not a package' : 'Not a package'}
            </Button>
          )}

          {/* Story P10-4.3: "Edited" indicator */}
          {wasEdited && editedTooltip && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded cursor-help">
                  edited
                </span>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-xs">{editedTooltip}</p>
              </TooltipContent>
            </Tooltip>
          )}
        </div>

        {/* Correction Input (shows on thumbs down for new feedback) */}
        {showCorrection && (
          <div className="flex flex-col gap-2 p-3 bg-muted rounded-lg border animate-in fade-in slide-in-from-top-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">What should it say? (optional)</span>
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
              value={correction}
              onChange={handleCorrectionChange}
              placeholder="Enter the correct description..."
              className="min-h-[80px] text-sm resize-none"
              maxLength={CORRECTION_MAX_LENGTH}
              aria-label="Correction text"
            />
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                {correction.length}/{CORRECTION_MAX_LENGTH}
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

        {/* Story P10-4.3: Edit Correction Input */}
        {editingCorrection && (
          <div className="flex flex-col gap-2 p-3 bg-muted rounded-lg border animate-in fade-in slide-in-from-top-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Edit correction</span>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleCancelEditCorrection}
                className="h-6 w-6 p-0"
                aria-label="Cancel editing"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            <Textarea
              value={editCorrection}
              onChange={handleEditCorrectionChange}
              placeholder="Enter the correct description..."
              className="min-h-[80px] text-sm resize-none"
              maxLength={CORRECTION_MAX_LENGTH}
              aria-label="Edit correction text"
            />
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                {editCorrection.length}/{CORRECTION_MAX_LENGTH}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCancelEditCorrection}
                  disabled={isPending}
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={handleSaveEditCorrection}
                  disabled={isPending}
                >
                  {isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    'Save'
                  )}
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Story P10-4.3: Remove Confirmation Dialog */}
        <AlertDialog open={showRemoveConfirm} onOpenChange={setShowRemoveConfirm}>
          <AlertDialogContent onClick={handleContainerClick}>
            <AlertDialogHeader>
              <AlertDialogTitle>Remove feedback?</AlertDialogTitle>
              <AlertDialogDescription>
                This will remove your feedback from this event. You can always add new feedback later.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={isPending}>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={handleConfirmRemove}
                disabled={isPending}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Removing...
                  </>
                ) : (
                  'Remove'
                )}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </TooltipProvider>
  );
});
