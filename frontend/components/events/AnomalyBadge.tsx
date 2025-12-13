/**
 * AnomalyBadge component - displays anomaly severity indicator on event cards
 * Story P4-7.3: Anomaly Alerts
 *
 * Shows visual badge for medium/high anomaly scores:
 * - No badge for low anomaly (<0.3)
 * - Yellow "Unusual" badge for medium anomaly (0.3-0.6)
 * - Red "Anomaly" badge for high anomaly (>0.6)
 */

'use client';

import { AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

// Severity thresholds matching backend AnomalyScoringService
const LOW_THRESHOLD = 0.3;
const HIGH_THRESHOLD = 0.6;

export type AnomalySeverity = 'low' | 'medium' | 'high';

interface AnomalyBadgeProps {
  /** Anomaly score from 0.0 to 1.0, or null if not scored */
  score: number | null | undefined;
  /** Whether to show tooltip with exact score on hover */
  showTooltip?: boolean;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Get severity level from anomaly score
 */
export function getAnomalySeverity(score: number | null | undefined): AnomalySeverity | null {
  if (score == null) return null;
  if (score < LOW_THRESHOLD) return 'low';
  if (score < HIGH_THRESHOLD) return 'medium';
  return 'high';
}

/**
 * Get display label for severity
 */
function getSeverityLabel(severity: AnomalySeverity): string {
  switch (severity) {
    case 'medium':
      return 'Unusual';
    case 'high':
      return 'Anomaly';
    default:
      return '';
  }
}

/**
 * Get CSS classes for severity badge styling
 */
function getSeverityClasses(severity: AnomalySeverity): string {
  switch (severity) {
    case 'medium':
      // Yellow/amber for medium anomaly
      return 'bg-amber-100 text-amber-700 border-amber-300';
    case 'high':
      // Red for high anomaly
      return 'bg-red-100 text-red-700 border-red-300';
    default:
      return '';
  }
}

/**
 * Get icon color for severity
 */
function getIconColor(severity: AnomalySeverity): string {
  switch (severity) {
    case 'medium':
      return 'text-amber-600';
    case 'high':
      return 'text-red-600';
    default:
      return 'text-gray-400';
  }
}

export function AnomalyBadge({
  score,
  showTooltip = true,
  className,
}: AnomalyBadgeProps) {
  const severity = getAnomalySeverity(score);

  // Don't show badge for low anomaly or null score
  if (!severity || severity === 'low') {
    return null;
  }

  const label = getSeverityLabel(severity);
  const badgeClasses = getSeverityClasses(severity);
  const iconColor = getIconColor(severity);

  const badge = (
    <span
      className={cn(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border',
        badgeClasses,
        className
      )}
      data-testid="anomaly-badge"
      data-severity={severity}
    >
      <AlertTriangle className={cn('w-3 h-3', iconColor)} />
      {label}
    </span>
  );

  if (!showTooltip || score == null) {
    return badge;
  }

  const tooltipText = `Anomaly score: ${(score * 100).toFixed(0)}%`;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          {badge}
        </TooltipTrigger>
        <TooltipContent>
          <p>{tooltipText}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
