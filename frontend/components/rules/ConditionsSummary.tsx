'use client';

import type { IAlertRuleConditions } from '@/types/alert-rule';
import { Badge } from '@/components/ui/badge';

interface ConditionsSummaryProps {
  conditions: IAlertRuleConditions;
  compact?: boolean;
}

export function ConditionsSummary({ conditions, compact = false }: ConditionsSummaryProps) {
  const parts: string[] = [];

  // Object types
  if (conditions.object_types && conditions.object_types.length > 0) {
    const types = conditions.object_types.map(t => capitalize(t));
    if (compact && types.length > 2) {
      parts.push(`${types.slice(0, 2).join(', ')} +${types.length - 2}`);
    } else {
      parts.push(types.join(', '));
    }
  }

  // Cameras
  if (conditions.cameras && conditions.cameras.length > 0) {
    parts.push(`${conditions.cameras.length} camera${conditions.cameras.length > 1 ? 's' : ''}`);
  }

  // Time of day
  if (conditions.time_of_day) {
    parts.push(`${conditions.time_of_day.start}-${conditions.time_of_day.end}`);
  }

  // Days of week
  if (conditions.days_of_week && conditions.days_of_week.length > 0 && conditions.days_of_week.length < 7) {
    const days = formatDaysOfWeek(conditions.days_of_week);
    parts.push(days);
  }

  // Confidence
  if (conditions.min_confidence !== undefined && conditions.min_confidence > 0) {
    parts.push(`${conditions.min_confidence}%+ confidence`);
  }

  if (parts.length === 0) {
    return <span className="text-muted-foreground text-sm">Any event</span>;
  }

  if (compact) {
    return (
      <div className="flex flex-wrap gap-1">
        {parts.slice(0, 3).map((part, i) => (
          <Badge key={i} variant="outline" className="text-xs font-normal">
            {part}
          </Badge>
        ))}
        {parts.length > 3 && (
          <Badge variant="outline" className="text-xs font-normal">
            +{parts.length - 3} more
          </Badge>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-wrap gap-1">
      {parts.map((part, i) => (
        <Badge key={i} variant="outline" className="text-xs font-normal">
          {part}
        </Badge>
      ))}
    </div>
  );
}

function capitalize(str: string): string {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function formatDaysOfWeek(days: number[]): string {
  const dayNames = ['', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const sorted = [...days].sort((a, b) => a - b);

  // Check for weekdays (1-5)
  if (sorted.length === 5 && sorted.every((d, i) => d === i + 1)) {
    return 'Weekdays';
  }

  // Check for weekends (6-7)
  if (sorted.length === 2 && sorted[0] === 6 && sorted[1] === 7) {
    return 'Weekends';
  }

  // Otherwise list them
  if (sorted.length <= 3) {
    return sorted.map(d => dayNames[d]).join(', ');
  }

  return `${sorted.length} days`;
}
