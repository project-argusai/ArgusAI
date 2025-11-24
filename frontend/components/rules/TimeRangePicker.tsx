'use client';

import { useState } from 'react';
import { UseFormReturn } from 'react-hook-form';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import type { RuleFormValues } from './RuleFormDialog';

interface TimeRangePickerProps {
  form: UseFormReturn<RuleFormValues>;
}

export function TimeRangePicker({ form }: TimeRangePickerProps) {
  const timeOfDay = form.watch('conditions.time_of_day');
  const [enabled, setEnabled] = useState(!!timeOfDay);

  const handleToggle = (checked: boolean) => {
    setEnabled(checked);
    if (checked) {
      form.setValue('conditions.time_of_day', { start: '09:00', end: '17:00' }, { shouldValidate: true });
    } else {
      form.setValue('conditions.time_of_day', null, { shouldValidate: true });
    }
  };

  const handleStartChange = (value: string) => {
    const current = form.getValues('conditions.time_of_day') || { start: '09:00', end: '17:00' };
    form.setValue('conditions.time_of_day', { ...current, start: value }, { shouldValidate: true });
  };

  const handleEndChange = (value: string) => {
    const current = form.getValues('conditions.time_of_day') || { start: '09:00', end: '17:00' };
    form.setValue('conditions.time_of_day', { ...current, end: value }, { shouldValidate: true });
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <Label>Time of Day</Label>
          <p className="text-sm text-muted-foreground">
            Only trigger during specific hours
          </p>
        </div>
        <Switch
          checked={enabled}
          onCheckedChange={handleToggle}
          aria-label="Enable time of day filter"
        />
      </div>

      {enabled && (
        <div className="flex items-center gap-2 pl-4">
          <div className="flex-1">
            <Label htmlFor="time-start" className="sr-only">Start time</Label>
            <Input
              id="time-start"
              type="time"
              value={timeOfDay?.start || '09:00'}
              onChange={(e) => handleStartChange(e.target.value)}
              className="w-full"
              aria-label="Start time"
            />
          </div>
          <span className="text-muted-foreground">to</span>
          <div className="flex-1">
            <Label htmlFor="time-end" className="sr-only">End time</Label>
            <Input
              id="time-end"
              type="time"
              value={timeOfDay?.end || '17:00'}
              onChange={(e) => handleEndChange(e.target.value)}
              className="w-full"
              aria-label="End time"
            />
          </div>
        </div>
      )}
    </div>
  );
}
