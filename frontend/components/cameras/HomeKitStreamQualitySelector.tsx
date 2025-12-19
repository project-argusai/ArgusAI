/**
 * HomeKit Stream Quality Selector Component (Story P7-3.1)
 * Provides UI for selecting HomeKit camera streaming quality:
 * - Low: 640x480, 15fps, 500kbps - Best for slow networks
 * - Medium: 1280x720, 25fps, 1500kbps - Balanced quality/bandwidth
 * - High: 1920x1080, 30fps, 3000kbps - Best quality, high bandwidth
 */

'use client';

import { UseFormReturn } from 'react-hook-form';
import { Wifi, WifiLow, Signal } from 'lucide-react';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
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
import type { HomeKitStreamQuality } from '@/types/camera';
import { cn } from '@/lib/utils';

interface HomeKitStreamQualitySelectorProps {
  /**
   * React Hook Form instance from parent CameraForm
   */
  form: UseFormReturn<CameraFormValues>;
}

/**
 * Stream quality configuration
 */
const STREAM_QUALITIES = {
  low: {
    value: 'low' as HomeKitStreamQuality,
    name: 'Low',
    description: '640x480 @ 15fps, 500kbps',
    details: 'Best for slow or congested networks. Lower bandwidth usage.',
    icon: WifiLow,
    resolution: '480p',
    bandwidth: '~0.5 Mbps',
  },
  medium: {
    value: 'medium' as HomeKitStreamQuality,
    name: 'Medium',
    description: '1280x720 @ 25fps, 1500kbps',
    details: 'Balanced quality and bandwidth. Recommended for most setups.',
    icon: Wifi,
    resolution: '720p',
    bandwidth: '~1.5 Mbps',
  },
  high: {
    value: 'high' as HomeKitStreamQuality,
    name: 'High',
    description: '1920x1080 @ 30fps, 3000kbps',
    details: 'Best quality for fast networks. Higher bandwidth usage.',
    icon: Signal,
    resolution: '1080p',
    bandwidth: '~3 Mbps',
  },
} as const;

/**
 * HomeKit Stream Quality Selector Component
 * Integrates with CameraForm to provide HomeKit streaming quality selection
 */
export function HomeKitStreamQualitySelector({ form }: HomeKitStreamQualitySelectorProps) {
  const currentValue = form.watch('homekit_stream_quality');

  return (
    <div className="space-y-4 border rounded-lg p-6 bg-muted/20">
      <div>
        <h3 className="text-lg font-semibold mb-1">HomeKit Stream Quality</h3>
        <p className="text-sm text-muted-foreground">
          Configure video quality for HomeKit camera streaming
        </p>
      </div>

      <FormField
        control={form.control}
        name="homekit_stream_quality"
        render={({ field }) => (
          <FormItem>
            <FormControl>
              <RadioGroup
                onValueChange={field.onChange}
                value={field.value || 'medium'}
                className="grid gap-3"
              >
                {Object.values(STREAM_QUALITIES).map((quality) => {
                  const Icon = quality.icon;
                  const isSelected = (field.value || 'medium') === quality.value;

                  return (
                    <TooltipProvider key={quality.value}>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <div
                            className={cn(
                              'relative flex items-center gap-4 rounded-lg border p-4 cursor-pointer transition-all',
                              isSelected && 'border-primary bg-primary/5',
                              !isSelected && 'hover:border-primary/50 hover:bg-muted/30'
                            )}
                            onClick={() => field.onChange(quality.value)}
                          >
                            <RadioGroupItem
                              value={quality.value}
                              id={`quality-${quality.value}`}
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
                                  htmlFor={`quality-${quality.value}`}
                                  className="font-medium cursor-pointer"
                                >
                                  {quality.name}
                                </Label>
                                {/* Resolution badge */}
                                <span className={cn(
                                  'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
                                  quality.value === 'low' && 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
                                  quality.value === 'medium' && 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
                                  quality.value === 'high' && 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                                )}>
                                  {quality.resolution}
                                </span>
                              </div>
                              <p className="text-sm text-muted-foreground">
                                {quality.description}
                              </p>
                            </div>

                            {/* Bandwidth indicator */}
                            <div className="text-sm text-muted-foreground">
                              {quality.bandwidth}
                            </div>

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
                            <p className="font-medium">{quality.name} Quality</p>
                            <p className="text-sm">{quality.details}</p>
                          </div>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  );
                })}
              </RadioGroup>
            </FormControl>

            <FormDescription className="mt-3">
              {currentValue === 'low' && 'Lower resolution reduces bandwidth usage. Ideal for remote viewing on slow connections.'}
              {currentValue === 'medium' && 'HD quality with moderate bandwidth. Works well for most home networks.'}
              {(currentValue === 'high' || !currentValue) && 'Full HD quality for the best viewing experience. Requires a stable, fast network.'}
            </FormDescription>
          </FormItem>
        )}
      />
    </div>
  );
}
