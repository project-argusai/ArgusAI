/**
 * ConfidenceIndicator - displays AI confidence level for an event
 *
 * Story P3-6.3: Shows confidence indicator with visual treatment:
 * - High (80-100): Green checkmark icon
 * - Medium (50-79): Amber dot icon
 * - Low (0-49): Red warning triangle icon
 *
 * Also shows low confidence warning when low_confidence flag is true,
 * and displays vague_reason in tooltip when present.
 */

'use client';

import { CheckCircle2, Circle, AlertTriangle } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { AIConfidenceLevel } from '@/types/event';

interface ConfidenceIndicatorProps {
  /** AI self-reported confidence score (0-100), null if not available */
  aiConfidence?: number | null;
  /** True if flagged as low confidence (ai_confidence < 50 OR vague) */
  lowConfidence?: boolean;
  /** Human-readable reason why flagged as vague */
  vagueReason?: string | null;
}

/**
 * Configuration for each confidence level
 */
const LEVEL_CONFIG: Record<
  AIConfidenceLevel,
  {
    icon: typeof CheckCircle2;
    label: string;
    description: string;
    bgClass: string;
    textClass: string;
  }
> = {
  high: {
    icon: CheckCircle2,
    label: 'High confidence',
    description: 'AI is certain about this description',
    bgClass: 'bg-green-100 dark:bg-green-900/30',
    textClass: 'text-green-700 dark:text-green-300',
  },
  medium: {
    icon: Circle,
    label: 'Medium confidence',
    description: 'Description may need verification',
    bgClass: 'bg-amber-100 dark:bg-amber-900/30',
    textClass: 'text-amber-700 dark:text-amber-300',
  },
  low: {
    icon: AlertTriangle,
    label: 'Low confidence',
    description: 'Consider re-analyzing this event',
    bgClass: 'bg-red-100 dark:bg-red-900/30',
    textClass: 'text-red-700 dark:text-red-300',
  },
};

/**
 * Get confidence level from score
 */
function getLevel(score: number): AIConfidenceLevel {
  if (score >= 80) return 'high';
  if (score >= 50) return 'medium';
  return 'low';
}

export function ConfidenceIndicator({
  aiConfidence,
  lowConfidence,
  vagueReason,
}: ConfidenceIndicatorProps) {
  // AC4: Handle null/undefined ai_confidence - show nothing
  if (aiConfidence == null) {
    return null;
  }

  const level = getLevel(aiConfidence);
  const config = LEVEL_CONFIG[level];
  const Icon = config.icon;
  const hasLowConfidenceWarning = lowConfidence === true;

  // Build screen reader text (AC6)
  const srText = [
    `${config.label}: ${aiConfidence}%`,
    hasLowConfidenceWarning && 'AI was uncertain about this description',
    vagueReason && `Reason: ${vagueReason}`,
  ]
    .filter(Boolean)
    .join('. ');

  // Build tooltip content (AC3, AC5)
  const tooltipContent = (
    <div className="space-y-1 text-xs">
      <p className="font-medium">Confidence: {aiConfidence}%</p>
      <p className="text-muted-foreground">{config.description}</p>
      {/* AC2: Show low confidence warning */}
      {hasLowConfidenceWarning && (
        <p className="text-amber-600 dark:text-amber-400 flex items-center gap-1 mt-1">
          <AlertTriangle className="h-3 w-3 shrink-0" />
          <span>AI was uncertain about this description</span>
        </p>
      )}
      {/* AC5: Show vague reason when present */}
      {vagueReason && (
        <p className="text-muted-foreground mt-1">
          Reason: {vagueReason}
        </p>
      )}
    </div>
  );

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium ${config.bgClass} ${config.textClass} cursor-help`}
          // AC6: Keyboard accessible via focus
          tabIndex={0}
        >
          <Icon className="h-3 w-3" aria-hidden="true" />
          <span>{aiConfidence}%</span>
          {/* AC2: Low confidence warning indicator */}
          {hasLowConfidenceWarning && level !== 'low' && (
            <AlertTriangle className="h-2.5 w-2.5 text-amber-500" aria-hidden="true" />
          )}
          {/* AC6: Screen reader text */}
          <span className="sr-only">{srText}</span>
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        {tooltipContent}
      </TooltipContent>
    </Tooltip>
  );
}
