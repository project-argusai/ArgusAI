/**
 * Prompt Refinement Modal Component
 * Story P8-3.3: AI-assisted prompt refinement using feedback data
 */

'use client';

import { useState, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Loader2, Sparkles, RefreshCw, ThumbsUp, ThumbsDown, AlertCircle } from 'lucide-react';
import { apiClient } from '@/lib/api-client';
import type { PromptRefinementResponse } from '@/lib/api-client';
import { toast } from 'sonner';

interface PromptRefinementModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentPrompt: string;
  onAccept: (newPrompt: string) => void;
}

export function PromptRefinementModal({
  open,
  onOpenChange,
  currentPrompt,
  onAccept,
}: PromptRefinementModalProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [refinementResult, setRefinementResult] = useState<PromptRefinementResponse | null>(null);
  const [editedPrompt, setEditedPrompt] = useState('');
  const [error, setError] = useState<string | null>(null);

  // Reset state when modal opens
  const handleOpenChange = useCallback((newOpen: boolean) => {
    if (newOpen) {
      // Modal opening - reset state and start refinement
      setRefinementResult(null);
      setEditedPrompt('');
      setError(null);
      // Auto-start refinement when modal opens
      handleRefine(currentPrompt);
    } else {
      // Modal closing - reset state
      setRefinementResult(null);
      setEditedPrompt('');
      setError(null);
      setIsLoading(false);
    }
    onOpenChange(newOpen);
  }, [currentPrompt, onOpenChange]);

  // Call the refinement API
  const handleRefine = async (promptToRefine: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const result = await apiClient.ai.refinePrompt({
        current_prompt: promptToRefine,
        include_feedback: true,
        max_feedback_samples: 50,
      });

      setRefinementResult(result);
      setEditedPrompt(result.suggested_prompt);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to refine prompt';

      // Check for specific error types
      if (errorMessage.includes('No feedback data available')) {
        setError('No feedback data available. Rate some event descriptions first to enable AI-assisted prompt improvement.');
      } else if (errorMessage.includes('No AI providers configured')) {
        setError('No AI providers configured. Please add an API key in Settings first.');
      } else {
        setError(errorMessage);
      }

      toast.error('Prompt refinement failed', {
        description: errorMessage,
      });
    } finally {
      setIsLoading(false);
    }
  };

  // Handle resubmit with edited prompt
  const handleResubmit = () => {
    if (editedPrompt.trim()) {
      handleRefine(editedPrompt);
    }
  };

  // Handle accept - save the new prompt
  const handleAccept = () => {
    if (editedPrompt.trim()) {
      onAccept(editedPrompt);
      toast.success('Prompt updated', {
        description: 'Your AI description prompt has been updated.',
      });
      onOpenChange(false);
    }
  };

  // Handle cancel
  const handleCancel = () => {
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-purple-500" />
            AI-Assisted Prompt Refinement
          </DialogTitle>
          <DialogDescription>
            Analyzing your feedback data to suggest an improved AI description prompt.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Current Prompt (read-only) */}
          <div className="space-y-2">
            <Label htmlFor="current-prompt">Current Prompt</Label>
            <Textarea
              id="current-prompt"
              value={currentPrompt}
              readOnly
              rows={3}
              className="bg-muted resize-none"
            />
          </div>

          {/* Loading State */}
          {isLoading && (
            <div className="flex flex-col items-center justify-center py-8 space-y-4">
              <Loader2 className="h-8 w-8 animate-spin text-purple-500" />
              <p className="text-sm text-muted-foreground">
                Analyzing feedback patterns and generating suggestions...
              </p>
            </div>
          )}

          {/* Error State */}
          {error && !isLoading && (
            <div className="flex items-start gap-3 p-4 bg-destructive/10 border border-destructive/20 rounded-md">
              <AlertCircle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
              <div className="space-y-1">
                <p className="text-sm font-medium text-destructive">Unable to Refine Prompt</p>
                <p className="text-sm text-muted-foreground">{error}</p>
              </div>
            </div>
          )}

          {/* Refinement Results */}
          {refinementResult && !isLoading && !error && (
            <>
              {/* Feedback Stats */}
              <div className="bg-muted p-4 rounded-md space-y-3">
                <p className="text-sm font-medium">Feedback Analyzed</p>
                <div className="flex items-center gap-6 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground">Total:</span>
                    <span className="font-medium">{refinementResult.feedback_analyzed}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <ThumbsUp className="h-4 w-4 text-green-500" />
                    <span className="font-medium">{refinementResult.positive_examples}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <ThumbsDown className="h-4 w-4 text-red-500" />
                    <span className="font-medium">{refinementResult.negative_examples}</span>
                  </div>
                </div>
              </div>

              {/* Changes Summary */}
              <div className="space-y-2">
                <Label>Changes Summary</Label>
                <p className="text-sm text-muted-foreground bg-muted p-3 rounded-md">
                  {refinementResult.changes_summary}
                </p>
              </div>

              {/* Suggested Prompt (editable) */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor="suggested-prompt">Suggested Prompt</Label>
                  <span className="text-xs text-muted-foreground">
                    {editedPrompt.length} characters
                  </span>
                </div>
                <Textarea
                  id="suggested-prompt"
                  value={editedPrompt}
                  onChange={(e) => setEditedPrompt(e.target.value)}
                  rows={6}
                  placeholder="Edit the suggested prompt..."
                  className="resize-none"
                />
                <p className="text-xs text-muted-foreground">
                  You can edit this prompt before accepting. Click &quot;Resubmit&quot; to get new suggestions based on your edits.
                </p>
              </div>
            </>
          )}
        </div>

        <DialogFooter className="flex-col sm:flex-row gap-2">
          <Button variant="outline" onClick={handleCancel}>
            Cancel
          </Button>

          {refinementResult && !isLoading && !error && (
            <>
              <Button
                variant="outline"
                onClick={handleResubmit}
                disabled={isLoading || !editedPrompt.trim()}
              >
                <RefreshCw className="h-4 w-4 mr-2" />
                Resubmit
              </Button>
              <Button
                onClick={handleAccept}
                disabled={isLoading || !editedPrompt.trim()}
              >
                Accept
              </Button>
            </>
          )}

          {/* Retry button for errors */}
          {error && !isLoading && (
            <Button
              variant="outline"
              onClick={() => handleRefine(currentPrompt)}
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Retry
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
