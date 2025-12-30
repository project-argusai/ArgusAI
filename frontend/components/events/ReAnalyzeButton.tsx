/**
 * ReAnalyzeButton - Button to trigger re-analysis of low-confidence events
 *
 * Story P3-6.4: Shows re-analyze button for events flagged with low_confidence.
 * Opens ReAnalyzeModal to select analysis mode.
 *
 * AC1: Only shows for events with low_confidence=true
 * AC1: Uses RefreshCw icon, styled to match existing action buttons
 */

'use client';

import { useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { ReAnalyzeModal } from './ReAnalyzeModal';
import type { IEvent } from '@/types/event';

interface ReAnalyzeButtonProps {
  /** Event to re-analyze */
  event: IEvent;
  /** Callback when re-analysis completes successfully */
  onReanalyze?: (updatedEvent: IEvent) => void;
  /** Whether the button is in loading state */
  isLoading?: boolean;
  /** Optional custom class name */
  className?: string;
}

/**
 * ReAnalyzeButton Component
 *
 * Displays a button to trigger re-analysis for low-confidence events.
 * Only renders when event.low_confidence is true.
 */
export function ReAnalyzeButton({
  event,
  onReanalyze,
  isLoading = false,
  className = '',
}: ReAnalyzeButtonProps) {
  const [isModalOpen, setIsModalOpen] = useState(false);

  // AC1: Only show for low confidence events
  if (!event.low_confidence) {
    return null;
  }

  const handleClick = () => {
    setIsModalOpen(true);
  };

  const handleClose = () => {
    setIsModalOpen(false);
  };

  const handleSuccess = (updatedEvent: IEvent) => {
    setIsModalOpen(false);
    onReanalyze?.(updatedEvent);
  };

  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleClick}
            disabled={isLoading}
            className={`h-7 px-2 text-muted-foreground hover:text-foreground ${className}`}
            aria-label="Re-analyze this event"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`}
              aria-hidden="true"
            />
            <span className="sr-only">Re-analyze</span>
          </Button>
        </TooltipTrigger>
        <TooltipContent side="top">
          <p>Re-analyze with better quality</p>
        </TooltipContent>
      </Tooltip>

      <ReAnalyzeModal
        event={event}
        isOpen={isModalOpen}
        onClose={handleClose}
        onSuccess={handleSuccess}
      />
    </>
  );
}
