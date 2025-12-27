/**
 * ReAnalyzeModal - Modal dialog for selecting re-analysis options
 *
 * Story P3-6.4: Displays re-analysis mode options with cost indicators.
 * Story P12-4.5: Enhanced with smart query mode showing relevance scores
 *
 * AC2: Shows analysis mode options with cost indicators ($, $$, $$$)
 * AC2: Disables unavailable modes with explanations
 * AC3: Triggers re-analysis API call on confirm
 * AC4: Updates event on success with toast notification
 * AC5: Handles errors with toast notification
 * AC8 (P12-4): Re-analyze modal shows relevance score (0-100) for each frame
 */

'use client';

import { useState, useEffect } from 'react';
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query';
import { RefreshCw, Info, Search, Sparkles, Loader2 } from 'lucide-react';
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
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
  const [activeTab, setActiveTab] = useState<'standard' | 'smart'>('standard');
  const [smartQuery, setSmartQuery] = useState('');
  const [lastResult, setLastResult] = useState<{
    frames_selected: number;
    frames_available: number;
    top_frame_score: number;
  } | null>(null);
  const queryClient = useQueryClient();

  const sourceType: SourceType = event.source_type || 'rtsp';
  const currentMode = event.analysis_mode || 'single_frame';
  const isProtectCamera = sourceType === 'protect';

  // Fetch query suggestions (Story P12-4.4)
  const { data: suggestionsData, isLoading: suggestionsLoading } = useQuery({
    queryKey: ['query-suggestions', event.id],
    queryFn: () => apiClient.events.getQuerySuggestions(event.id),
    enabled: isOpen && activeTab === 'smart',
    staleTime: 60000, // 1 minute
  });

  // AC3: Mutation for standard re-analysis API call
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

  // Mutation for smart re-analysis (Story P12-4.5)
  const smartReanalyzeMutation = useMutation({
    mutationFn: async () => {
      return apiClient.events.smartReanalyze(event.id, smartQuery, {
        top_k: 5,
        use_cache: true,
        analysis_mode: 'multi_frame',
      });
    },
    onSuccess: (result) => {
      setLastResult({
        frames_selected: result.frames_selected,
        frames_available: result.frames_available,
        top_frame_score: result.top_frame_score,
      });

      toast.success('Smart analysis complete', {
        description: `Selected ${result.frames_selected} of ${result.frames_available} frames (${Math.round(result.top_frame_score * 100)}% relevance)`,
      });

      // Invalidate event queries to refresh the list
      queryClient.invalidateQueries({ queryKey: ['events'] });
      queryClient.invalidateQueries({ queryKey: ['event', event.id] });

      // Don't close immediately - let user see the results
    },
    onError: (error: Error) => {
      let errorMessage = 'Smart analysis failed';

      if (error.message.includes('400') && error.message.includes('frame embeddings')) {
        errorMessage = 'No frame embeddings available. Try standard re-analysis first.';
      } else if (error.message.includes('429')) {
        errorMessage = 'Rate limit exceeded. Please try again later.';
      }

      toast.error('Smart analysis failed', {
        description: errorMessage,
      });
    },
  });

  const handleConfirm = () => {
    if (activeTab === 'smart') {
      if (!smartQuery.trim()) {
        toast.error('Please enter a query');
        return;
      }
      smartReanalyzeMutation.mutate();
    } else {
      reanalyzeMutation.mutate();
    }
  };

  const handleModeChange = (value: string) => {
    setSelectedMode(value as AnalysisMode);
  };

  const handleSuggestionClick = (suggestion: string) => {
    setSmartQuery(suggestion);
  };

  const isPending = reanalyzeMutation.isPending || smartReanalyzeMutation.isPending;

  // Reset state when modal closes
  useEffect(() => {
    if (!isOpen) {
      setActiveTab('standard');
      setSmartQuery('');
      setLastResult(null);
    }
  }, [isOpen]);

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <RefreshCw className="h-5 w-5" />
            Re-Analyze Event
          </DialogTitle>
          <DialogDescription>
            Choose an analysis mode or ask a specific question about this event.
          </DialogDescription>
        </DialogHeader>

        {/* Tabbed interface (Story P12-4.5) */}
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'standard' | 'smart')}>
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="standard">
              <RefreshCw className="h-4 w-4 mr-2" />
              Standard
            </TabsTrigger>
            <TabsTrigger value="smart" disabled={!isProtectCamera}>
              <Sparkles className="h-4 w-4 mr-2" />
              Smart Query
              {!isProtectCamera && (
                <span className="ml-1 text-xs text-muted-foreground">(Protect only)</span>
              )}
            </TabsTrigger>
          </TabsList>

          {/* Standard Re-analysis Tab */}
          <TabsContent value="standard" className="space-y-4">
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
                        disabled={!isAvailable || isPending}
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
          </TabsContent>

          {/* Smart Query Tab (Story P12-4.5) */}
          <TabsContent value="smart" className="space-y-4">
            <div className="flex items-center gap-2 px-3 py-2 bg-primary/5 rounded-md text-sm">
              <Sparkles className="h-4 w-4 text-primary shrink-0" />
              <span className="text-muted-foreground">
                Ask a specific question and AI will focus on the most relevant frames.
              </span>
            </div>

            {/* Query input */}
            <div className="space-y-2">
              <Label htmlFor="smart-query">Your question</Label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  id="smart-query"
                  placeholder="e.g., Was there a package delivery?"
                  value={smartQuery}
                  onChange={(e) => setSmartQuery(e.target.value)}
                  className="pl-10"
                  disabled={isPending}
                />
              </div>
            </div>

            {/* Query suggestions (AC7) */}
            {suggestionsLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading suggestions...
              </div>
            ) : suggestionsData?.suggestions && suggestionsData.suggestions.length > 0 ? (
              <div className="space-y-2">
                <Label className="text-xs text-muted-foreground">Suggested questions</Label>
                <div className="flex flex-wrap gap-2">
                  {suggestionsData.suggestions.map((suggestion, idx) => (
                    <Badge
                      key={idx}
                      variant="outline"
                      className="cursor-pointer hover:bg-primary/10 hover:border-primary transition-colors"
                      onClick={() => handleSuggestionClick(suggestion)}
                    >
                      {suggestion}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}

            {/* Results display (AC8 - relevance scores) */}
            {lastResult && (
              <div className="p-3 rounded-lg border bg-green-50 dark:bg-green-900/20 space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium text-green-700 dark:text-green-300">
                  <Sparkles className="h-4 w-4" />
                  Analysis Complete
                </div>
                <div className="grid grid-cols-3 gap-2 text-sm">
                  <div className="text-center p-2 bg-background rounded">
                    <div className="text-2xl font-bold text-primary">
                      {lastResult.frames_selected}
                    </div>
                    <div className="text-xs text-muted-foreground">Frames Selected</div>
                  </div>
                  <div className="text-center p-2 bg-background rounded">
                    <div className="text-2xl font-bold">
                      {lastResult.frames_available}
                    </div>
                    <div className="text-xs text-muted-foreground">Total Frames</div>
                  </div>
                  <div className="text-center p-2 bg-background rounded">
                    <div className="text-2xl font-bold text-amber-600 dark:text-amber-400">
                      {Math.round(lastResult.top_frame_score * 100)}%
                    </div>
                    <div className="text-xs text-muted-foreground">Top Relevance</div>
                  </div>
                </div>
              </div>
            )}
          </TabsContent>
        </Tabs>

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
            disabled={isPending}
          >
            {lastResult ? 'Close' : 'Cancel'}
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={isPending || (activeTab === 'smart' && !smartQuery.trim())}
          >
            {isPending ? (
              <>
                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                {activeTab === 'smart' ? 'Analyzing...' : 'Re-analyzing...'}
              </>
            ) : activeTab === 'smart' ? (
              <>
                <Sparkles className="h-4 w-4 mr-2" />
                Ask AI
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
