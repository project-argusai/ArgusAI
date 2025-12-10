/**
 * ReanalyzedIndicator - Shows when an event has been re-analyzed
 *
 * Story P3-6.4 AC7: Shows "Re-analyzed on {date}" indicator for events
 * that have been re-analyzed.
 */

'use client';

import { RefreshCw } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';

interface ReanalyzedIndicatorProps {
  /** Timestamp when event was re-analyzed (ISO 8601), null if never re-analyzed */
  reanalyzedAt?: string | null;
}

/**
 * Parse timestamp as UTC
 */
function parseUTCTimestamp(timestamp: string): Date {
  const ts = timestamp.includes('Z') || timestamp.includes('+') || timestamp.includes('-', 10)
    ? timestamp
    : timestamp.replace(' ', 'T') + 'Z';
  return new Date(ts);
}

/**
 * ReanalyzedIndicator Component
 *
 * Displays a badge indicating when an event was re-analyzed.
 * Only renders when reanalyzed_at is present.
 */
export function ReanalyzedIndicator({ reanalyzedAt }: ReanalyzedIndicatorProps) {
  // AC7: Only show if event has been re-analyzed
  if (!reanalyzedAt) {
    return null;
  }

  const reanalyzedDate = parseUTCTimestamp(reanalyzedAt);
  const relativeTime = formatDistanceToNow(reanalyzedDate, { addSuffix: true });

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 cursor-help"
          tabIndex={0}
        >
          <RefreshCw className="h-3 w-3" aria-hidden="true" />
          <span>Re-analyzed</span>
          <span className="sr-only">Re-analyzed {relativeTime}</span>
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        <div className="text-xs">
          <p className="font-medium">Re-analyzed {relativeTime}</p>
          <p className="text-muted-foreground">
            {reanalyzedDate.toLocaleString()}
          </p>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}
