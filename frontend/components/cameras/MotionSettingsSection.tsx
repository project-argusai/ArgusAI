/**
 * Motion Detection Settings Section
 * Provides UI controls for configuring motion detection parameters:
 * - Sensitivity level (Low, Medium, High)
 * - Algorithm selection (MOG2, KNN, Frame Differencing)
 * - Cooldown period (5-300 seconds)
 */

'use client';

import { UseFormReturn } from 'react-hook-form';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { HelpCircle } from 'lucide-react';
import type { CameraFormValues } from '@/lib/validations/camera';

interface MotionSettingsSectionProps {
  /**
   * React Hook Form instance from parent CameraForm
   */
  form: UseFormReturn<CameraFormValues>;
}

/**
 * Algorithm descriptions for tooltips
 */
const ALGORITHM_DESCRIPTIONS = {
  mog2: 'Mixture of Gaussians (MOG2): Fast and accurate background subtraction. Recommended for most use cases.',
  knn: 'K-Nearest Neighbors (KNN): Better accuracy with slight performance trade-off. Good for complex scenes.',
  frame_diff: 'Frame Differencing: Fastest algorithm but less accurate. Best for static cameras with simple scenes.',
} as const;

/**
 * Sensitivity level descriptions
 */
const SENSITIVITY_DESCRIPTIONS = {
  low: 'Detects only large, obvious movements (person walking). Fewer false positives.',
  medium: 'Balanced detection (person waving, pet moving). Recommended default.',
  high: 'Detects small movements (leaves, curtains, small animals). More false positives.',
} as const;

/**
 * Motion Settings Section Component
 * Integrates with CameraForm to provide motion detection configuration UI
 */
export function MotionSettingsSection({ form }: MotionSettingsSectionProps) {
  return (
    <div className="space-y-6 border rounded-lg p-6 bg-muted/20">
      <div>
        <h3 className="text-lg font-semibold mb-1">Motion Detection Settings</h3>
        <p className="text-sm text-muted-foreground">
          Configure motion detection sensitivity, algorithm, and cooldown period
        </p>
      </div>

      {/* Motion Sensitivity */}
      <FormField
        control={form.control}
        name="motion_sensitivity"
        render={({ field }) => (
          <FormItem>
            <FormLabel className="flex items-center gap-2">
              Motion Sensitivity
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <HelpCircle className="h-4 w-4 text-muted-foreground cursor-help" />
                  </TooltipTrigger>
                  <TooltipContent className="max-w-xs">
                    <p className="text-sm">
                      Controls how much motion is needed to trigger an event:
                    </p>
                    <ul className="text-xs mt-2 space-y-1 list-disc list-inside">
                      <li>Low: Large movements only (5% frame change)</li>
                      <li>Medium: Balanced (2% frame change)</li>
                      <li>High: Small movements (0.5% frame change)</li>
                    </ul>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </FormLabel>
            <Select onValueChange={field.onChange} defaultValue={field.value}>
              <FormControl>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                <SelectItem value="low">
                  <div className="flex flex-col items-start">
                    <span>Low</span>
                    <span className="text-xs text-muted-foreground">
                      Large movements only
                    </span>
                  </div>
                </SelectItem>
                <SelectItem value="medium">
                  <div className="flex flex-col items-start">
                    <span>Medium (Recommended)</span>
                    <span className="text-xs text-muted-foreground">
                      Balanced detection
                    </span>
                  </div>
                </SelectItem>
                <SelectItem value="high">
                  <div className="flex flex-col items-start">
                    <span>High</span>
                    <span className="text-xs text-muted-foreground">
                      Sensitive to small movements
                    </span>
                  </div>
                </SelectItem>
              </SelectContent>
            </Select>
            <FormDescription>
              {SENSITIVITY_DESCRIPTIONS[field.value as keyof typeof SENSITIVITY_DESCRIPTIONS]}
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />

      {/* Motion Detection Algorithm */}
      <FormField
        control={form.control}
        name="motion_algorithm"
        render={({ field }) => (
          <FormItem>
            <FormLabel className="flex items-center gap-2">
              Detection Algorithm
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <HelpCircle className="h-4 w-4 text-muted-foreground cursor-help" />
                  </TooltipTrigger>
                  <TooltipContent className="max-w-xs">
                    <p className="text-sm">
                      The computer vision algorithm used to detect motion:
                    </p>
                    <ul className="text-xs mt-2 space-y-1 list-disc list-inside">
                      <li>MOG2: Best for most use cases (30-50ms)</li>
                      <li>KNN: Better accuracy, slight slowdown (40-60ms)</li>
                      <li>Frame Diff: Fastest but less accurate (20-30ms)</li>
                    </ul>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </FormLabel>
            <Select onValueChange={field.onChange} defaultValue={field.value}>
              <FormControl>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                <SelectItem value="mog2">
                  <div className="flex flex-col items-start">
                    <span>MOG2 (Recommended)</span>
                    <span className="text-xs text-muted-foreground">
                      Fast and accurate
                    </span>
                  </div>
                </SelectItem>
                <SelectItem value="knn">
                  <div className="flex flex-col items-start">
                    <span>KNN</span>
                    <span className="text-xs text-muted-foreground">
                      Better accuracy, slight slowdown
                    </span>
                  </div>
                </SelectItem>
                <SelectItem value="frame_diff">
                  <div className="flex flex-col items-start">
                    <span>Frame Differencing</span>
                    <span className="text-xs text-muted-foreground">
                      Fastest, less accurate
                    </span>
                  </div>
                </SelectItem>
              </SelectContent>
            </Select>
            <FormDescription>
              {ALGORITHM_DESCRIPTIONS[field.value as keyof typeof ALGORITHM_DESCRIPTIONS]}
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />

      {/* Cooldown Period */}
      <FormField
        control={form.control}
        name="motion_cooldown"
        render={({ field }) => (
          <FormItem>
            <FormLabel className="flex items-center gap-2">
              Cooldown Period (seconds)
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <HelpCircle className="h-4 w-4 text-muted-foreground cursor-help" />
                  </TooltipTrigger>
                  <TooltipContent className="max-w-xs">
                    <p className="text-sm">
                      Time between motion events. Prevents repeated triggers from continuous motion.
                      Range: 5-300 seconds. Recommended: 30-60 seconds.
                    </p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </FormLabel>
            <FormControl>
              <Input
                type="number"
                min={5}
                max={300}
                placeholder="30"
                {...field}
                onChange={(e) =>
                  field.onChange(e.target.value ? parseInt(e.target.value) : undefined)
                }
                value={field.value ?? ''}
              />
            </FormControl>
            <FormDescription>
              Wait time between motion events (5-300 seconds). Default: 30 seconds.
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
    </div>
  );
}
