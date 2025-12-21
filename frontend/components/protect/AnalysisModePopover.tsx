/**
 * Analysis Mode Popover Component for Protect Cameras
 * Story P3-3.3: Build Analysis Mode Selector UI Component
 *
 * Allows users to configure AI analysis mode for Protect cameras
 * directly from the discovered camera list in Settings.
 *
 * Features:
 * - Three analysis mode options with icons and cost indicators
 * - Tooltips explaining each mode
 * - Apply/Cancel buttons for saving or reverting
 * - Loading state while saving
 */

'use client';

import { useState, useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Image, Images, Video, Loader2, Sparkles } from 'lucide-react';

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { apiClient } from '@/lib/api-client';
import type { AnalysisMode } from '@/types/camera';

/**
 * Analysis mode configuration
 */
const ANALYSIS_MODES = {
  single_frame: {
    value: 'single_frame' as AnalysisMode,
    name: 'Single Frame',
    description: 'Fastest, lowest cost. Uses event thumbnail only.',
    icon: Image,
    cost: '$',
  },
  multi_frame: {
    value: 'multi_frame' as AnalysisMode,
    name: 'Multi-Frame',
    description: 'Balanced. Extracts 5 frames from video clip.',
    icon: Images,
    cost: '$$',
  },
  video_native: {
    value: 'video_native' as AnalysisMode,
    name: 'Video Native',
    description: 'Best quality, higher cost. Sends full video to AI.',
    icon: Video,
    cost: '$$$',
  },
} as const;

export interface AnalysisModePopoverProps {
  /** Camera database ID (from cameras table) */
  cameraId: string;
  /** Current analysis mode */
  currentMode: AnalysisMode;
  /** Whether camera is enabled for AI */
  isEnabled: boolean;
  /** Callback when mode is updated */
  onModeUpdated?: () => void;
}

export function AnalysisModePopover({
  cameraId,
  currentMode,
  isEnabled,
  onModeUpdated,
}: AnalysisModePopoverProps) {
  const queryClient = useQueryClient();
  const [isOpen, setIsOpen] = useState(false);
  const [selectedMode, setSelectedMode] = useState<AnalysisMode>(currentMode);

  // Reset local state when popover opens
  useEffect(() => {
    if (isOpen) {
      setSelectedMode(currentMode);
    }
  }, [isOpen, currentMode]);

  // Mutation for updating analysis mode
  const modeMutation = useMutation({
    mutationFn: (mode: AnalysisMode) =>
      apiClient.cameras.update(cameraId, { analysis_mode: mode }),
    onSuccess: () => {
      toast.success('Analysis mode updated');
      // Invalidate camera queries to refresh
      queryClient.invalidateQueries({ queryKey: ['cameras'] });
      setIsOpen(false);
      onModeUpdated?.();
    },
    onError: () => {
      toast.error('Failed to update analysis mode');
    },
  });

  // Handle Apply button
  const handleApply = () => {
    if (selectedMode !== currentMode) {
      modeMutation.mutate(selectedMode);
    } else {
      setIsOpen(false);
    }
  };

  // Handle Cancel button
  const handleCancel = () => {
    setIsOpen(false);
  };

  // Get current mode config for badge
  const currentModeConfig = ANALYSIS_MODES[currentMode];

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          disabled={!isEnabled}
          className="gap-1"
        >
          <Sparkles className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">AI Mode</span>
          <span className={cn(
            'ml-1 text-xs font-medium',
            currentMode === 'single_frame' && 'text-green-600',
            currentMode === 'multi_frame' && 'text-blue-600',
            currentMode === 'video_native' && 'text-purple-600'
          )}>
            {currentModeConfig.cost}
          </span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80" align="end">
        <div className="space-y-4">
          {/* Header */}
          <div className="font-medium">AI Analysis Mode</div>
          <p className="text-xs text-muted-foreground">
            Choose how the AI analyzes events from this camera.
          </p>
          <div className="border-t" />

          {/* Analysis Mode Radio Group */}
          <RadioGroup
            value={selectedMode}
            onValueChange={(value) => setSelectedMode(value as AnalysisMode)}
            className="space-y-2"
          >
            {Object.values(ANALYSIS_MODES).map((mode) => {
              const Icon = mode.icon;
              const isSelected = selectedMode === mode.value;

              return (
                <TooltipProvider key={mode.value}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div
                        className={cn(
                          'flex items-center gap-3 p-2 rounded-md cursor-pointer transition-colors',
                          isSelected && 'bg-primary/10 border border-primary/30',
                          !isSelected && 'hover:bg-muted'
                        )}
                        onClick={() => setSelectedMode(mode.value)}
                      >
                        <RadioGroupItem
                          value={mode.value}
                          id={`mode-${mode.value}`}
                          className="sr-only"
                        />
                        <div className={cn(
                          'flex h-8 w-8 shrink-0 items-center justify-center rounded-md',
                          isSelected ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
                        )}>
                          <Icon className="h-4 w-4" />
                        </div>
                        <div className="flex-1">
                          <Label
                            htmlFor={`mode-${mode.value}`}
                            className="font-medium cursor-pointer"
                          >
                            {mode.name}
                          </Label>
                        </div>
                        <span className={cn(
                          'text-xs font-medium px-1.5 py-0.5 rounded',
                          mode.value === 'single_frame' && 'bg-green-100 text-green-700',
                          mode.value === 'multi_frame' && 'bg-blue-100 text-blue-700',
                          mode.value === 'video_native' && 'bg-purple-100 text-purple-700'
                        )}>
                          {mode.cost}
                        </span>
                      </div>
                    </TooltipTrigger>
                    <TooltipContent side="left">
                      <p>{mode.description}</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              );
            })}
          </RadioGroup>

          <div className="border-t" />

          {/* Action Buttons */}
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleCancel}
              disabled={modeMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleApply}
              disabled={modeMutation.isPending}
            >
              {modeMutation.isPending ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                  Saving...
                </>
              ) : (
                'Apply'
              )}
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

/**
 * Helper to get analysis mode display text
 */
export function getAnalysisModeDisplayText(mode: AnalysisMode | undefined): string {
  if (!mode) return 'Single Frame';
  return ANALYSIS_MODES[mode]?.name ?? 'Single Frame';
}
