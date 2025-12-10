/**
 * ReAnalyzeModal - Modal dialog for selecting re-analysis options
 *
 * Story P3-6.4: Displays re-analysis mode options with cost indicators.
 * Disables modes not available for the camera type.
 *
 * AC2: Shows analysis mode options with cost indicators ($, $$, $$$)
 * AC2: Disables unavailable modes with explanations
 * AC3: Triggers re-analysis API call on confirm
 * AC4: Updates event on success with toast notification
 * AC5: Handles errors with toast notification
 */

'use client';

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { RefreshCw, Info } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api-client';
import type { IEvent, AnalysisMode, SourceType } from '@/types/event';

interface ReAnalyzeModalProps {
  /** Event to re-analyze */
  event: IEvent;
  /** Whether the modal is open */
  isOpen: boolean;
  /** Callback when modal is closed */
  onClose: () => void;
  /** Callback when re-analysis completes successfully */
  onSuccess?: (updatedEvent: IEvent) => void;
}

/**
 * Analysis mode option configuration
 */
interface ModeOption {
  value: AnalysisMode;
  label: string;
  description: string;
  costIndicator: string;
  availableFor: SourceType[];
  disabledReason?: (sourceType: SourceType) => string | undefined;
}

const MODE_OPTIONS: ModeOption[] = [
  {
    value: 'single_frame',
    label: 'Single Frame',
    description: 'Re-analyze using the stored thumbnail image',
    costIndicator: '$',
    availableFor: ['protect', 'rtsp', 'usb'],
  },
  {
    value: 'multi_frame',
    label: 'Multi-Frame',
    description: 'Extract and analyze multiple frames from video clip',
    costIndicator: '$$',
    availableFor: ['protect'],
    disabledReason: (sourceType) =>
      sourceType === 'protect'
        ? undefined
        : 'Multi-frame analysis requires a UniFi Protect camera',
  },
  {
    value: 'video_native',
    label: 'Video Native',
    description: 'Send full video clip to AI for comprehensive analysis',
    costIndicator: '$$$',
    availableFor: ['protect'],
    disabledReason: (sourceType) =>
      sourceType === 'protect'
        ? undefined
        : 'Video native analysis requires a UniFi Protect camera',
  },
];

/**
 * Get mode display name
 */
function getModeDisplayName(mode: string | null | undefined): string {
  if (!mode) return 'Unknown';
  switch (mode) {
    case 'single_frame':
      return 'Single Frame';
    case 'multi_frame':
      return 'Multi-Frame';
    case 'video_native':
      return 'Video Native';
    default:
      return mode;
  }
}

export function ReAnalyzeModal({
  event,
  isOpen,
  onClose,
  onSuccess,
}: ReAnalyzeModalProps) {
  const [selectedMode, setSelectedMode] = useState<AnalysisMode>('single_frame');
  const queryClient = useQueryClient();

  const sourceType: SourceType = event.source_type || 'rtsp';
  const currentMode = event.analysis_mode || 'single_frame';

  // AC3: Mutation for re-analysis API call
  const reanalyzeMutation = useMutation({
    mutationFn: async () => {
      return apiClient.events.reanalyze(event.id, selectedMode);
    },
    onSuccess: (updatedEvent) => {
      // AC4: Show success toast
      toast.success('Event re-analyzed successfully', {
        description: `New confidence: ${updatedEvent.ai_confidence ?? 'N/A'}%`,
      });

      // Invalidate event queries to refresh the list
      queryClient.invalidateQueries({ queryKey: ['events'] });
      queryClient.invalidateQueries({ queryKey: ['event', event.id] });

      // Call success callback
      onSuccess?.(updatedEvent);
    },
    onError: (error: Error) => {
      // AC5: Show error toast
      let errorMessage = 'Failed to re-analyze event';

      // Check for rate limit error
      if (error.message.includes('429') || error.message.includes('rate limit')) {
        errorMessage = 'Rate limit exceeded. Please try again later (max 3 per hour).';
      } else if (error.message.includes('400')) {
        errorMessage = error.message || 'Invalid analysis mode for this camera type';
      }

      toast.error('Re-analysis failed', {
        description: errorMessage,
      });
    },
  });

  const handleConfirm = () => {
    reanalyzeMutation.mutate();
  };

  const handleModeChange = (value: string) => {
    setSelectedMode(value as AnalysisMode);
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <RefreshCw className="h-5 w-5" />
            Re-Analyze Event
          </DialogTitle>
          <DialogDescription>
            Choose an analysis mode to improve the description quality.
            Higher-cost modes may provide better results.
          </DialogDescription>
        </DialogHeader>

        {/* Current analysis info */}
        <div className="flex items-center gap-2 px-3 py-2 bg-muted/50 rounded-md text-sm">
          <Info className="h-4 w-4 text-muted-foreground shrink-0" />
          <span className="text-muted-foreground">
            Current mode: <span className="font-medium text-foreground">{getModeDisplayName(currentMode)}</span>
          </span>
        </div>

        {/* AC2: Mode selection with cost indicators */}
        <RadioGroup
          value={selectedMode}
          onValueChange={handleModeChange}
          className="space-y-3"
        >
          {MODE_OPTIONS.map((option) => {
            const isAvailable = option.availableFor.includes(sourceType);
            const disabledReason = option.disabledReason?.(sourceType);

            return (
              <div key={option.value} className="relative">
                <div
                  className={`flex items-start space-x-3 rounded-lg border p-3 transition-colors ${
                    isAvailable
                      ? 'cursor-pointer hover:bg-muted/50'
                      : 'opacity-50 cursor-not-allowed bg-muted/30'
                  } ${selectedMode === option.value && isAvailable ? 'border-primary bg-primary/5' : ''}`}
                >
                  <RadioGroupItem
                    value={option.value}
                    id={option.value}
                    disabled={!isAvailable || reanalyzeMutation.isPending}
                    className="mt-1"
                  />
                  <div className="flex-1 space-y-1">
                    <Label
                      htmlFor={option.value}
                      className={`flex items-center gap-2 font-medium ${
                        isAvailable ? 'cursor-pointer' : 'cursor-not-allowed'
                      }`}
                    >
                      <span>{option.label}</span>
                      <span
                        className={`text-xs px-1.5 py-0.5 rounded ${
                          option.costIndicator === '$'
                            ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                            : option.costIndicator === '$$'
                            ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
                            : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                        }`}
                      >
                        {option.costIndicator}
                      </span>
                    </Label>
                    <p className="text-sm text-muted-foreground">
                      {option.description}
                    </p>
                    {/* AC2: Show reason why mode is disabled */}
                    {!isAvailable && disabledReason && (
                      <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                        {disabledReason}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </RadioGroup>

        {/* Rate limit info */}
        {(event.reanalysis_count ?? 0) > 0 && (
          <p className="text-xs text-muted-foreground">
            This event has been re-analyzed {event.reanalysis_count} time{event.reanalysis_count !== 1 ? 's' : ''}.
            Limit: 3 per hour.
          </p>
        )}

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="outline"
            onClick={onClose}
            disabled={reanalyzeMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={reanalyzeMutation.isPending}
          >
            {reanalyzeMutation.isPending ? (
              <>
                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                Re-analyzing...
              </>
            ) : (
              'Confirm'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
