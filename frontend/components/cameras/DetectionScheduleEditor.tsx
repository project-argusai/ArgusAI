/**
 * Detection Schedule Editor Component
 * Provides UI for configuring time-based and day-based detection schedules
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
import { Label } from '@/components/ui/label';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { HelpCircle, Clock } from 'lucide-react';
import type { CameraFormValues } from '@/lib/validations/camera';
import type { IDetectionSchedule } from '@/types/camera';

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
 * Calculate schedule status based on current time and configuration
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

  // Check if current time is within range
  const { start_time, end_time } = schedule;

  // Safety check for time values
  if (!start_time || !end_time) {
    return {
      status: 'always-active',
      label: 'Always Active (No Schedule)',
      color: 'text-blue-600',
    };
  }

  // Handle overnight schedules (e.g., 22:00 - 06:00)
  const isOvernight = start_time > end_time;

  const isActive = isOvernight
    ? currentTime >= start_time || currentTime < end_time
    : currentTime >= start_time && currentTime < end_time;

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
 */
export function DetectionScheduleEditor({ form }: DetectionScheduleEditorProps) {
  const schedule = form.watch('detection_schedule');
  const scheduleStatus = calculateScheduleStatus(schedule);

  // Check if overnight schedule
  const isOvernightSchedule =
    schedule?.enabled &&
    schedule.start_time &&
    schedule.end_time &&
    schedule.start_time > schedule.end_time;

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
                      start_time: '09:00',
                      end_time: '17:00',
                      days: [0, 1, 2, 3, 4], // Weekdays
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
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              {/* Start Time */}
              <FormField
                control={form.control}
                name="detection_schedule.start_time"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Start Time</FormLabel>
                    <FormControl>
                      <Input
                        type="time"
                        {...field}
                        value={field.value || ''}
                      />
                    </FormControl>
                    <FormDescription>
                      24-hour format
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* End Time */}
              <FormField
                control={form.control}
                name="detection_schedule.end_time"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>End Time</FormLabel>
                    <FormControl>
                      <Input
                        type="time"
                        {...field}
                        value={field.value || ''}
                      />
                    </FormControl>
                    <FormDescription>
                      24-hour format
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {/* Time Range Display */}
            {schedule.start_time && schedule.end_time && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <span className="font-medium">Active window:</span>
                <span>
                  {schedule.start_time} - {schedule.end_time}
                  {isOvernightSchedule && (
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span className="ml-2 text-amber-600 font-medium">
                            (Overnight)
                          </span>
                        </TooltipTrigger>
                        <TooltipContent className="max-w-xs">
                          <p className="text-sm">
                            This schedule crosses midnight. Detection will be active from{' '}
                            {schedule.start_time} until {schedule.end_time} the next day.
                          </p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  )}
                </span>
              </div>
            )}
          </div>

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
