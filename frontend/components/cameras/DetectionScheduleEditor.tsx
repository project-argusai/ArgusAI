/**
 * Detection Schedule Editor Component
 * Provides UI for configuring time-based and day-based detection schedules
 * Updated in Phase 5 (P5-5.4) to support multiple time ranges
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
import { Label } from '@/components/ui/label';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { HelpCircle, Clock } from 'lucide-react';
import type { CameraFormValues } from '@/lib/validations/camera';
import type { IDetectionSchedule, ITimeRange } from '@/types/camera';
import { MultiTimeRangePicker } from './MultiTimeRangePicker';

interface DetectionScheduleEditorProps {
  /**
   * React Hook Form instance from parent CameraForm
   */
  form: UseFormReturn<CameraFormValues>;
}

/**
 * Day of week labels and values
 * Maps to backend day numbering (0=Monday, 6=Sunday per Python weekday())
 */
const DAYS_OF_WEEK = [
  { label: 'Monday', value: 0 },
  { label: 'Tuesday', value: 1 },
  { label: 'Wednesday', value: 2 },
  { label: 'Thursday', value: 3 },
  { label: 'Friday', value: 4 },
  { label: 'Saturday', value: 5 },
  { label: 'Sunday', value: 6 },
] as const;

/**
 * Check if a time is within a single range (handles overnight ranges)
 */
function isTimeInRange(currentTime: string, range: ITimeRange): boolean {
  const { start_time, end_time } = range;
  const isOvernight = start_time > end_time;

  if (isOvernight) {
    // Overnight range: active if >= start OR < end
    return currentTime >= start_time || currentTime < end_time;
  } else {
    // Normal range: active if >= start AND < end
    return currentTime >= start_time && currentTime < end_time;
  }
}

/**
 * Migrate legacy schedule format to new time_ranges format
 * Used when loading existing schedules that use start_time/end_time at root
 */
export function migrateScheduleFormat(schedule: IDetectionSchedule): IDetectionSchedule {
  // If already using time_ranges, return as-is
  if (schedule.time_ranges && schedule.time_ranges.length > 0) {
    return schedule;
  }

  // If has legacy format, migrate to time_ranges
  if (schedule.start_time && schedule.end_time) {
    return {
      enabled: schedule.enabled,
      days: schedule.days,
      time_ranges: [
        { start_time: schedule.start_time, end_time: schedule.end_time }
      ],
    };
  }

  // Default: return with empty time_ranges (will use defaults)
  return {
    enabled: schedule.enabled,
    days: schedule.days,
    time_ranges: [{ start_time: '09:00', end_time: '17:00' }],
  };
}

/**
 * Calculate schedule status based on current time and configuration
 * Updated in Phase 5 (P5-5.4) to support multiple time ranges
 */
function calculateScheduleStatus(schedule: IDetectionSchedule | null | undefined): {
  status: 'active' | 'inactive' | 'always-active';
  label: string;
  color: string;
} {
  if (!schedule || !schedule.enabled) {
    return {
      status: 'always-active',
      label: 'Always Active (No Schedule)',
      color: 'text-blue-600',
    };
  }

  const now = new Date();
  const currentDay = (now.getDay() + 6) % 7; // Convert JS day (0=Sunday) to Python day (0=Monday)
  const currentTime = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;

  // Check if current day is in selected days
  if (!schedule.days || !schedule.days.includes(currentDay)) {
    return {
      status: 'inactive',
      label: 'Inactive (Outside Schedule)',
      color: 'text-gray-500',
    };
  }

  // Phase 5 (P5-5.4): Support multiple time ranges
  const timeRanges = schedule.time_ranges;

  if (timeRanges && timeRanges.length > 0) {
    // Check if current time is within ANY of the ranges
    const isActiveInAnyRange = timeRanges.some((range) => {
      if (!range.start_time || !range.end_time) return false;
      return isTimeInRange(currentTime, range);
    });

    return isActiveInAnyRange
      ? {
          status: 'active',
          label: 'Active Now',
          color: 'text-green-600',
        }
      : {
          status: 'inactive',
          label: 'Inactive (Outside Schedule)',
          color: 'text-gray-500',
        };
  }

  // Legacy fallback: single start_time/end_time at root level
  const { start_time, end_time } = schedule;

  // Safety check for time values
  if (!start_time || !end_time) {
    return {
      status: 'always-active',
      label: 'Always Active (No Schedule)',
      color: 'text-blue-600',
    };
  }

  const isActive = isTimeInRange(currentTime, { start_time, end_time });

  return isActive
    ? {
        status: 'active',
        label: 'Active Now',
        color: 'text-green-600',
      }
    : {
        status: 'inactive',
        label: 'Inactive (Outside Schedule)',
        color: 'text-gray-500',
      };
}

/**
 * Detection Schedule Editor Component
 * Integrates with CameraForm to provide schedule configuration UI
 * Updated in Phase 5 (P5-5.4) to support multiple time ranges
 */
export function DetectionScheduleEditor({ form }: DetectionScheduleEditorProps) {
  const schedule = form.watch('detection_schedule');
  const scheduleStatus = calculateScheduleStatus(schedule);

  // Get time ranges, with migration support for legacy format
  const getTimeRanges = (): ITimeRange[] => {
    if (!schedule) return [{ start_time: '09:00', end_time: '17:00' }];

    // If already using new format
    if (schedule.time_ranges && schedule.time_ranges.length > 0) {
      return schedule.time_ranges;
    }

    // Migrate from legacy format
    if (schedule.start_time && schedule.end_time) {
      return [{ start_time: schedule.start_time, end_time: schedule.end_time }];
    }

    // Default
    return [{ start_time: '09:00', end_time: '17:00' }];
  };

  // Check if any range is overnight
  const hasOvernightRange = schedule?.enabled && schedule.time_ranges?.some(
    (range: ITimeRange) => range.start_time > range.end_time
  );

  return (
    <div className="space-y-6 border rounded-lg p-6 bg-muted/20">
      <div>
        <h3 className="text-lg font-semibold mb-1">Detection Schedule</h3>
        <p className="text-sm text-muted-foreground">
          Configure when motion detection is active based on time and day
        </p>
      </div>

      {/* Schedule Enable/Disable Toggle */}
      <FormField
        control={form.control}
        name="detection_schedule.enabled"
        render={({ field }) => (
          <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
            <div className="space-y-0.5">
              <FormLabel className="text-base">
                Enable Detection Schedule
              </FormLabel>
              <FormDescription>
                Restrict motion detection to specific times and days
              </FormDescription>
            </div>
            <FormControl>
              <button
                type="button"
                role="switch"
                aria-checked={field.value || false}
                onClick={() => {
                  const newValue = !(field.value || false);
                  field.onChange(newValue);

                  // Initialize schedule with defaults if enabling for first time
                  if (newValue && !schedule) {
                    form.setValue('detection_schedule', {
                      enabled: true,
                      time_ranges: [{ start_time: '09:00', end_time: '17:00' }],
                      days: [0, 1, 2, 3, 4], // Weekdays
                    });
                  } else if (newValue && schedule && !schedule.time_ranges) {
                    // Migrate legacy format when enabling
                    const migrated = migrateScheduleFormat(schedule);
                    form.setValue('detection_schedule', {
                      ...migrated,
                      enabled: true,
                    });
                  } else if (!newValue && schedule) {
                    // When disabling, set enabled to false but keep config
                    form.setValue('detection_schedule', {
                      ...schedule,
                      enabled: false,
                    });
                  }
                }}
                className={`
                  relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50
                  ${field.value ? 'bg-blue-600' : 'bg-gray-300'}
                `}
              >
                <span
                  className={`
                    inline-block h-5 w-5 transform rounded-full bg-white transition-transform
                    ${field.value ? 'translate-x-6' : 'translate-x-0.5'}
                  `}
                />
              </button>
            </FormControl>
          </FormItem>
        )}
      />

      {/* Schedule Status Indicator */}
      {schedule && (
        <div className="flex items-center gap-2 p-3 rounded-md bg-muted/50">
          <Clock className={`h-4 w-4 ${scheduleStatus.color}`} />
          <span className={`text-sm font-medium ${scheduleStatus.color}`}>
            {scheduleStatus.label}
          </span>
        </div>
      )}

      {/* Time Range Selectors (only show if schedule is enabled) */}
      {schedule?.enabled && (
        <>
          {/* Multiple Time Ranges Picker - Phase 5 (P5-5.4) */}
          <FormField
            control={form.control}
            name="detection_schedule.time_ranges"
            render={({ field, fieldState }) => (
              <FormItem>
                <FormControl>
                  <MultiTimeRangePicker
                    value={field.value || getTimeRanges()}
                    onChange={(newRanges) => {
                      // Update time_ranges in the schedule
                      form.setValue('detection_schedule', {
                        ...schedule,
                        time_ranges: newRanges,
                        // Clear legacy fields when using new format
                        start_time: undefined,
                        end_time: undefined,
                      });
                    }}
                    maxRanges={4}
                    error={fieldState.error?.message}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* Day of Week Selection */}
          <FormField
            control={form.control}
            name="detection_schedule.days"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="flex items-center gap-2">
                  Active Days
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <HelpCircle className="h-4 w-4 text-muted-foreground cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent className="max-w-xs">
                        <p className="text-sm">
                          Select which days of the week motion detection should be active.
                          At least one day must be selected.
                        </p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </FormLabel>
                <div className="grid grid-cols-7 gap-2 pt-2">
                  {DAYS_OF_WEEK.map((day) => {
                    const isSelected = field.value?.includes(day.value) || false;
                    return (
                      <div key={day.value} className="flex flex-col items-center">
                        <button
                          type="button"
                          onClick={() => {
                            const currentDays = field.value || [];
                            const newDays = isSelected
                              ? currentDays.filter((d) => d !== day.value)
                              : [...currentDays, day.value].sort((a, b) => a - b);
                            field.onChange(newDays);
                          }}
                          className={`
                            w-full px-2 py-2 rounded-md text-xs font-medium transition-colors
                            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring
                            ${
                              isSelected
                                ? 'bg-blue-600 text-white hover:bg-blue-700'
                                : 'bg-muted text-muted-foreground hover:bg-muted/80'
                            }
                          `}
                        >
                          {day.label.slice(0, 3)}
                        </button>
                        <Label className="text-xs text-muted-foreground mt-1">
                          {day.label.slice(0, 1)}
                        </Label>
                      </div>
                    );
                  })}
                </div>
                <FormDescription>
                  Select days when motion detection should be active
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </>
      )}

      {/* Disabled state message */}
      {!schedule?.enabled && (
        <p className="text-sm text-muted-foreground italic">
          Schedule is disabled. Motion detection will run 24/7 on all days.
        </p>
      )}
    </div>
  );
}
