'use client';

import { UseFormReturn } from 'react-hook-form';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { DAYS_OF_WEEK } from '@/types/alert-rule';
import type { RuleFormValues } from './RuleFormDialog';

interface DaysOfWeekSelectorProps {
  form: UseFormReturn<RuleFormValues>;
}

export function DaysOfWeekSelector({ form }: DaysOfWeekSelectorProps) {
  const selectedDays = form.watch('conditions.days_of_week') || [1, 2, 3, 4, 5, 6, 7];

  const handleToggle = (day: number) => {
    const current = form.getValues('conditions.days_of_week') || [1, 2, 3, 4, 5, 6, 7];
    const updated = current.includes(day)
      ? current.filter((d: number) => d !== day)
      : [...current, day].sort((a, b) => a - b);
    form.setValue('conditions.days_of_week', updated, { shouldValidate: true });
  };

  const handleSelectWeekdays = () => {
    form.setValue('conditions.days_of_week', [1, 2, 3, 4, 5], { shouldValidate: true });
  };

  const handleSelectWeekends = () => {
    form.setValue('conditions.days_of_week', [6, 7], { shouldValidate: true });
  };

  const handleSelectAll = () => {
    form.setValue('conditions.days_of_week', [1, 2, 3, 4, 5, 6, 7], { shouldValidate: true });
  };

  return (
    <div className="space-y-2">
      <Label>Days of Week</Label>
      <p className="text-sm text-muted-foreground mb-2">
        Select which days the rule should be active
      </p>

      {/* Quick select buttons */}
      <div className="flex gap-2 mb-3">
        <button
          type="button"
          onClick={handleSelectAll}
          className="text-xs text-primary hover:underline rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
        >
          All days
        </button>
        <span className="text-muted-foreground">|</span>
        <button
          type="button"
          onClick={handleSelectWeekdays}
          className="text-xs text-primary hover:underline rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
        >
          Weekdays
        </button>
        <span className="text-muted-foreground">|</span>
        <button
          type="button"
          onClick={handleSelectWeekends}
          className="text-xs text-primary hover:underline rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
        >
          Weekends
        </button>
      </div>

      <div className="flex flex-wrap gap-3">
        {DAYS_OF_WEEK.map((day) => (
          <div key={day.value} className="flex items-center space-x-2">
            <Checkbox
              id={`day-${day.value}`}
              checked={selectedDays.includes(day.value)}
              onCheckedChange={() => handleToggle(day.value)}
              aria-label={`Select ${day.fullLabel}`}
            />
            <Label
              htmlFor={`day-${day.value}`}
              className="text-sm font-normal cursor-pointer"
            >
              {day.label}
            </Label>
          </div>
        ))}
      </div>
    </div>
  );
}
