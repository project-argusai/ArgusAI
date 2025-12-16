/**
 * MultiTimeRangePicker Component
 * Allows users to add/remove multiple time ranges for detection schedules
 * Phase 5 - Story P5-5.4
 */

'use client';

import { Plus, Trash2, Clock, AlertCircle } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { ITimeRange } from '@/types/camera';

interface MultiTimeRangePickerProps {
  /**
   * Array of time ranges
   */
  value: ITimeRange[];

  /**
   * Callback when ranges change
   */
  onChange: (ranges: ITimeRange[]) => void;

  /**
   * Maximum number of time ranges allowed
   * @default 4
   */
  maxRanges?: number;

  /**
   * Whether the picker is disabled
   * @default false
   */
  disabled?: boolean;

  /**
   * Validation error message to display
   */
  error?: string;
}

/**
 * Check if a time range is overnight (crosses midnight)
 */
function isOvernightRange(range: ITimeRange): boolean {
  return range.start_time > range.end_time;
}

/**
 * Generate a default time range
 */
function getDefaultTimeRange(): ITimeRange {
  return {
    start_time: '09:00',
    end_time: '17:00',
  };
}

/**
 * MultiTimeRangePicker Component
 * Provides UI for managing multiple detection time ranges
 */
export function MultiTimeRangePicker({
  value,
  onChange,
  maxRanges = 4,
  disabled = false,
  error,
}: MultiTimeRangePickerProps) {
  // Ensure we have at least one range
  const ranges = value.length > 0 ? value : [getDefaultTimeRange()];
  const canAddMore = ranges.length < maxRanges && !disabled;
  const canRemove = ranges.length > 1 && !disabled;

  /**
   * Update a specific range's start or end time
   */
  const handleRangeChange = (index: number, field: 'start_time' | 'end_time', newValue: string) => {
    const newRanges = [...ranges];
    newRanges[index] = {
      ...newRanges[index],
      [field]: newValue,
    };
    onChange(newRanges);
  };

  /**
   * Add a new time range
   */
  const handleAddRange = () => {
    if (!canAddMore) return;

    // Try to find a reasonable default for the new range
    // Add it after the last range's end time if possible
    const lastRange = ranges[ranges.length - 1];
    let newRange: ITimeRange;

    if (lastRange && lastRange.end_time < '20:00') {
      // Add a range 1 hour after the last one ends
      const [hours] = lastRange.end_time.split(':').map(Number);
      const newStartHour = Math.min(hours + 1, 23);
      const newEndHour = Math.min(newStartHour + 3, 23);
      newRange = {
        start_time: `${String(newStartHour).padStart(2, '0')}:00`,
        end_time: `${String(newEndHour).padStart(2, '0')}:00`,
      };
    } else {
      newRange = getDefaultTimeRange();
    }

    onChange([...ranges, newRange]);
  };

  /**
   * Remove a time range by index
   */
  const handleRemoveRange = (index: number) => {
    if (!canRemove) return;
    const newRanges = ranges.filter((_, i) => i !== index);
    onChange(newRanges);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Label className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-muted-foreground" />
          Active Time Ranges
          <span className="text-xs text-muted-foreground">
            ({ranges.length}/{maxRanges})
          </span>
        </Label>

        {canAddMore && (
          <button
            type="button"
            onClick={handleAddRange}
            disabled={!canAddMore}
            aria-label="Add another time range"
            className="flex items-center gap-1 text-sm text-primary hover:text-primary/80
                     focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2
                     disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            Add Range
          </button>
        )}
      </div>

      {/* Time Ranges List */}
      <div className="space-y-3">
        {ranges.map((range, index) => {
          const isOvernight = isOvernightRange(range);

          return (
            <div
              key={index}
              className="flex items-center gap-3 p-3 rounded-lg border bg-muted/10"
            >
              {/* Range Number */}
              <span className="text-sm font-medium text-muted-foreground w-6">
                #{index + 1}
              </span>

              {/* Start Time */}
              <div className="flex-1">
                <Label htmlFor={`range-${index}-start`} className="sr-only">
                  Range {index + 1} start time
                </Label>
                <Input
                  id={`range-${index}-start`}
                  type="time"
                  value={range.start_time}
                  onChange={(e) => handleRangeChange(index, 'start_time', e.target.value)}
                  disabled={disabled}
                  aria-label={`Time range ${index + 1} start time`}
                  className="text-center"
                />
              </div>

              {/* Separator */}
              <span className="text-muted-foreground font-medium">to</span>

              {/* End Time */}
              <div className="flex-1">
                <Label htmlFor={`range-${index}-end`} className="sr-only">
                  Range {index + 1} end time
                </Label>
                <Input
                  id={`range-${index}-end`}
                  type="time"
                  value={range.end_time}
                  onChange={(e) => handleRangeChange(index, 'end_time', e.target.value)}
                  disabled={disabled}
                  aria-label={`Time range ${index + 1} end time`}
                  className="text-center"
                />
              </div>

              {/* Overnight Indicator */}
              {isOvernight && (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="text-amber-600 font-medium text-xs px-2 py-0.5 rounded bg-amber-100/50">
                        Overnight
                      </span>
                    </TooltipTrigger>
                    <TooltipContent className="max-w-xs">
                      <p className="text-sm">
                        This range crosses midnight. Detection will be active from{' '}
                        {range.start_time} until {range.end_time} the next day.
                      </p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}

              {/* Remove Button */}
              {canRemove && (
                <button
                  type="button"
                  onClick={() => handleRemoveRange(index)}
                  disabled={!canRemove}
                  aria-label={`Remove time range ${index + 1}`}
                  className="p-2 text-destructive hover:text-destructive/80 hover:bg-destructive/10 rounded-md
                           focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2
                           disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </button>
              )}

              {/* Placeholder for spacing when remove button is hidden */}
              {!canRemove && <div className="w-10" />}
            </div>
          );
        })}
      </div>

      {/* Error Message */}
      {error && (
        <div className="flex items-center gap-2 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      {/* Help Text */}
      <p className="text-xs text-muted-foreground">
        Add multiple time ranges for when detection should be active.
        Detection is active if the current time falls within any of the ranges.
      </p>
    </div>
  );
}
