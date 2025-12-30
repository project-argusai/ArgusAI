/**
 * Analysis Mode Selector Component
 * Provides UI for selecting AI analysis mode per camera:
 * - Single Frame: Fastest, lowest cost ($)
 * - Multi-Frame: Balanced ($$)
 * - Video Native: Best quality, highest cost ($$$) - Protect cameras only
 */

'use client';

import { UseFormReturn } from 'react-hook-form';
import { Image, Images, Video, AlertTriangle } from 'lucide-react';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormMessage,
} from '@/components/ui/form';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Label } from '@/components/ui/label';
import type { CameraFormValues } from '@/lib/validations/camera';
import type { CameraSourceType, AnalysisMode } from '@/types/camera';
import { cn } from '@/lib/utils';

interface AnalysisModeSelectorProps {
  /**
   * React Hook Form instance from parent CameraForm
   */
  form: UseFormReturn<CameraFormValues>;
  /**
   * Camera source type - determines if video_native is available
   */
  sourceType: CameraSourceType;
}

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
    quality: 'Basic',
    speed: 'Fastest',
  },
  multi_frame: {
    value: 'multi_frame' as AnalysisMode,
    name: 'Multi-Frame',
    description: 'Balanced. Extracts 5 frames from video clip.',
    icon: Images,
    cost: '$$',
    quality: 'Good',
    speed: 'Moderate',
  },
  video_native: {
    value: 'video_native' as AnalysisMode,
    name: 'Video Native',
    description: 'Best quality, higher cost. Sends full video to AI.',
    icon: Video,
    cost: '$$$',
    quality: 'Best',
    speed: 'Slowest',
    restriction: 'Requires UniFi Protect camera',
  },
} as const;

/**
 * Analysis Mode Selector Component
 * Integrates with CameraForm to provide AI analysis mode selection
 */
export function AnalysisModeSelector({ form, sourceType }: AnalysisModeSelectorProps) {
  const isVideoNativeAvailable = sourceType === 'protect';
  const currentValue = form.watch('analysis_mode');

  return (
    <div className="space-y-4 border rounded-lg p-6 bg-muted/20">
      <div>
        <h3 className="text-lg font-semibold mb-1">AI Analysis Mode</h3>
        <p className="text-sm text-muted-foreground">
          Choose how the AI analyzes events from this camera
        </p>
      </div>

      <FormField
        control={form.control}
        name="analysis_mode"
        render={({ field }) => (
          <FormItem>
            <FormControl>
              <RadioGroup
                onValueChange={field.onChange}
                value={field.value}
                className="grid gap-3"
              >
                {Object.values(ANALYSIS_MODES).map((mode) => {
                  const Icon = mode.icon;
                  const isDisabled = mode.value === 'video_native' && !isVideoNativeAvailable;
                  const isSelected = field.value === mode.value;

                  return (
                    <TooltipProvider key={mode.value}>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <div
                            className={cn(
                              'relative flex items-center gap-4 rounded-lg border p-4 cursor-pointer transition-all',
                              isSelected && 'border-primary bg-primary/5',
                              isDisabled && 'opacity-50 cursor-not-allowed bg-muted/50',
                              !isSelected && !isDisabled && 'hover:border-primary/50 hover:bg-muted/30'
                            )}
                            onClick={() => {
                              if (!isDisabled) {
                                field.onChange(mode.value);
                              }
                            }}
                          >
                            <RadioGroupItem
                              value={mode.value}
                              id={mode.value}
                              disabled={isDisabled}
                              className="sr-only"
                            />

                            {/* Icon */}
                            <div className={cn(
                              'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
                              isSelected ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
                            )}>
                              <Icon className="h-5 w-5" />
                            </div>

                            {/* Content */}
                            <div className="flex-1 space-y-1">
                              <div className="flex items-center gap-2">
                                <Label
                                  htmlFor={mode.value}
                                  className={cn(
                                    'font-medium cursor-pointer',
                                    isDisabled && 'cursor-not-allowed'
                                  )}
                                >
                                  {mode.name}
                                </Label>
                                {/* Cost indicator badge */}
                                <span className={cn(
                                  'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
                                  mode.value === 'single_frame' && 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
                                  mode.value === 'multi_frame' && 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
                                  mode.value === 'video_native' && 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400'
                                )}>
                                  {mode.cost}
                                </span>
                              </div>
                              <p className="text-sm text-muted-foreground">
                                {mode.quality} quality &bull; {mode.speed}
                              </p>
                            </div>

                            {/* Warning for disabled video_native */}
                            {isDisabled && (
                              <div className="flex items-center gap-1.5 text-amber-600 dark:text-amber-500">
                                <AlertTriangle className="h-4 w-4" />
                              </div>
                            )}

                            {/* Selected indicator */}
                            {isSelected && (
                              <div className="absolute right-4 top-1/2 -translate-y-1/2">
                                <div className="h-2 w-2 rounded-full bg-primary" />
                              </div>
                            )}
                          </div>
                        </TooltipTrigger>
                        <TooltipContent side="right" className="max-w-xs">
                          <div className="space-y-1">
                            <p className="font-medium">{mode.name}</p>
                            <p className="text-sm">{mode.description}</p>
                            {isDisabled && 'restriction' in mode && (
                              <p className="text-sm text-amber-600 dark:text-amber-400 flex items-center gap-1 mt-2">
                                <AlertTriangle className="h-3 w-3" />
                                {mode.restriction}
                              </p>
                            )}
                          </div>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  );
                })}
              </RadioGroup>
            </FormControl>

            {/* Warning message for non-Protect cameras */}
            {!isVideoNativeAvailable && currentValue === 'video_native' && (
              <div className="flex items-center gap-2 mt-2 p-2 rounded-md bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800">
                <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
                <span className="text-sm text-amber-700 dark:text-amber-300">
                  Video Native requires UniFi Protect camera
                </span>
              </div>
            )}

            <FormDescription className="mt-3">
              {currentValue === 'single_frame' && 'Uses the event thumbnail for AI analysis. Fast and cost-effective.'}
              {currentValue === 'multi_frame' && 'Extracts multiple frames from the video clip for better context.'}
              {currentValue === 'video_native' && 'Sends the full video clip to AI providers that support video analysis.'}
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
    </div>
  );
}
