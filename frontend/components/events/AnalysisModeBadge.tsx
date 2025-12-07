/**
 * AnalysisModeBadge - displays the analysis mode used for an event
 *
 * Story P3-3.4: Shows compact badge with mode abbreviation (SF/MF/VN),
 * color-coded icons, and tooltip with full details.
 *
 * Colors follow AnalysisModeSelector pattern:
 * - Single Frame (SF): Gray
 * - Multi-Frame (MF): Blue
 * - Video Native (VN): Purple
 *
 * Shows fallback indicator when fallback_reason is present.
 */

'use client';

import { Image, Images, Video, AlertTriangle } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { AnalysisMode } from '@/types/event';

interface AnalysisModeBadgeProps {
  analysisMode?: AnalysisMode | null;
  frameCountUsed?: number | null;
  fallbackReason?: string | null;
}

/**
 * Configuration for each analysis mode
 */
const MODE_CONFIG: Record<
  AnalysisMode,
  {
    icon: typeof Image;
    abbrev: string;
    label: string;
    description: string;
    bgClass: string;
    textClass: string;
  }
> = {
  single_frame: {
    icon: Image,
    abbrev: 'SF',
    label: 'Single Frame',
    description: 'Uses event thumbnail only',
    bgClass: 'bg-gray-100 dark:bg-gray-800',
    textClass: 'text-gray-700 dark:text-gray-300',
  },
  multi_frame: {
    icon: Images,
    abbrev: 'MF',
    label: 'Multi-Frame',
    description: 'Extracts multiple frames from video clip',
    bgClass: 'bg-blue-100 dark:bg-blue-900/30',
    textClass: 'text-blue-700 dark:text-blue-300',
  },
  video_native: {
    icon: Video,
    abbrev: 'VN',
    label: 'Video Native',
    description: 'Full video clip sent to AI',
    bgClass: 'bg-purple-100 dark:bg-purple-900/30',
    textClass: 'text-purple-700 dark:text-purple-300',
  },
};

export function AnalysisModeBadge({
  analysisMode,
  frameCountUsed,
  fallbackReason,
}: AnalysisModeBadgeProps) {
  // AC3: Handle null/undefined analysis_mode - show nothing
  if (!analysisMode) {
    return null;
  }

  const config = MODE_CONFIG[analysisMode];

  if (!config) {
    return null;
  }

  const Icon = config.icon;
  const hasFallback = !!fallbackReason;

  // Build tooltip content
  const tooltipContent = (
    <div className="space-y-1 text-xs">
      <p className="font-medium">{config.label}</p>
      <p className="text-muted-foreground">{config.description}</p>
      {/* AC4: Show frame count if multi-frame */}
      {analysisMode === 'multi_frame' && frameCountUsed && (
        <p className="text-muted-foreground">Frames analyzed: {frameCountUsed}</p>
      )}
      {/* AC2: Show fallback reason if present */}
      {hasFallback && (
        <p className="text-amber-600 dark:text-amber-400 flex items-center gap-1 mt-1">
          <AlertTriangle className="h-3 w-3 shrink-0" />
          <span>Fell back to {config.label}: {fallbackReason}</span>
        </p>
      )}
    </div>
  );

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium ${config.bgClass} ${config.textClass} cursor-help`}
        >
          <Icon className="h-3 w-3" aria-hidden="true" />
          <span>{config.abbrev}</span>
          {/* AC2: Fallback indicator */}
          {hasFallback && (
            <AlertTriangle className="h-2.5 w-2.5 text-amber-500" aria-hidden="true" />
          )}
          <span className="sr-only">
            Analysis mode: {config.label}
            {hasFallback && `, fell back due to: ${fallbackReason}`}
          </span>
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        {tooltipContent}
      </TooltipContent>
    </Tooltip>
  );
}
