/**
 * FrameGalleryModal component - displays stored AI analysis frames in a lightbox
 * Story P8-2.2: Display Analysis Frames Gallery on Event Cards
 *
 * Fetches frames from the API and displays them in a navigable gallery modal.
 * Supports keyboard navigation (arrow keys, Escape) and shows timestamp offsets.
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import { Film, ChevronLeft, ChevronRight, X, AlertCircle, Loader2 } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api-client';

interface FrameGalleryModalProps {
  /** Event ID to fetch frames for */
  eventId: string;
  /** Whether the modal is open */
  open: boolean;
  /** Callback when modal should close */
  onOpenChange: (open: boolean) => void;
}

/**
 * Format timestamp offset in milliseconds to human-readable format
 * e.g., 1500 -> "+1.5s", 0 -> "+0.0s"
 */
function formatTimestampOffset(offsetMs: number): string {
  const seconds = offsetMs / 1000;
  return `+${seconds.toFixed(1)}s`;
}

export function FrameGalleryModal({ eventId, open, onOpenChange }: FrameGalleryModalProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);

  // Fetch frames when modal opens
  const {
    data: framesData,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['event-frames', eventId],
    queryFn: () => apiClient.events.getFrames(eventId),
    enabled: open && !!eventId,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  const frames = framesData?.frames ?? [];
  const hasFrames = frames.length > 0;

  // Reset selected index when modal opens or frames change
  useEffect(() => {
    if (open) {
      setSelectedIndex(0);
    }
  }, [open, eventId]);

  // Navigate to previous/next frame
  const navigateFrame = useCallback((direction: 'prev' | 'next') => {
    if (!hasFrames) return;

    setSelectedIndex((prev) => {
      if (direction === 'prev' && prev > 0) {
        return prev - 1;
      } else if (direction === 'next' && prev < frames.length - 1) {
        return prev + 1;
      }
      return prev;
    });
  }, [hasFrames, frames.length]);

  // Keyboard navigation (Task 5)
  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case 'ArrowLeft':
          e.preventDefault();
          navigateFrame('prev');
          break;
        case 'ArrowRight':
          e.preventDefault();
          navigateFrame('next');
          break;
        case 'Escape':
          // Dialog handles Escape by default, but ensure it works
          e.preventDefault();
          onOpenChange(false);
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, navigateFrame, onOpenChange]);

  // Build frame image URL using the API helper
  const getFrameImageUrl = (frameNumber: number): string => {
    return apiClient.events.getFrameUrl(eventId, frameNumber);
  };

  // Current frame data
  const currentFrame = hasFrames ? frames[selectedIndex] : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Film className="w-5 h-5 text-purple-500" />
            Analysis Frames
            {hasFrames && (
              <span className="text-sm font-normal text-muted-foreground ml-2">
                Frame {selectedIndex + 1} of {frames.length}
              </span>
            )}
          </DialogTitle>
        </DialogHeader>

        {/* Loading state */}
        {isLoading && (
          <div className="flex flex-col items-center justify-center py-16">
            <Loader2 className="w-8 h-8 animate-spin text-purple-500 mb-4" />
            <p className="text-muted-foreground">Loading frames...</p>
          </div>
        )}

        {/* Error state (Task 8) */}
        {error && !isLoading && (
          <div className="flex flex-col items-center justify-center py-16">
            <AlertCircle className="w-12 h-12 text-red-500 mb-4" />
            <p className="text-red-600 font-medium mb-2">Failed to load frames</p>
            <p className="text-sm text-muted-foreground mb-4">
              {error instanceof Error ? error.message : 'Unknown error'}
            </p>
            <Button variant="outline" onClick={() => refetch()}>
              Try Again
            </Button>
          </div>
        )}

        {/* Empty state (Task 6) */}
        {!isLoading && !error && !hasFrames && (
          <div className="flex flex-col items-center justify-center py-16">
            <AlertCircle className="w-12 h-12 text-gray-400 mb-4" />
            <p className="text-gray-600 font-medium mb-2">
              No analysis frames available
            </p>
            <p className="text-sm text-muted-foreground text-center max-w-md">
              This event was processed using single-frame analysis mode,
              which only uses the thumbnail for AI analysis.
              Multi-frame analysis stores additional frames for review.
            </p>
          </div>
        )}

        {/* Frame gallery (Task 4) */}
        {!isLoading && !error && hasFrames && currentFrame && (
          <>
            {/* Main frame view */}
            <div className="relative bg-black rounded-lg overflow-hidden">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={getFrameImageUrl(currentFrame.frame_number)}
                alt={`Analysis frame ${currentFrame.frame_number}`}
                className="w-full h-auto max-h-[50vh] object-contain mx-auto"
              />

              {/* Navigation arrows (AC2.3) */}
              {frames.length > 1 && (
                <>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="absolute left-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white rounded-full disabled:opacity-30"
                    onClick={() => navigateFrame('prev')}
                    disabled={selectedIndex === 0}
                    aria-label="Previous frame"
                  >
                    <ChevronLeft className="w-6 h-6" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="absolute right-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white rounded-full disabled:opacity-30"
                    onClick={() => navigateFrame('next')}
                    disabled={selectedIndex === frames.length - 1}
                    aria-label="Next frame"
                  >
                    <ChevronRight className="w-6 h-6" />
                  </Button>
                </>
              )}

              {/* Frame info overlay (AC2.4, AC2.5) */}
              <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-4">
                <div className="flex items-center justify-between text-white">
                  <div className="flex items-center gap-4">
                    <span className="text-sm font-medium">
                      Frame {currentFrame.frame_number} of {frames.length}
                    </span>
                    <span className="text-sm text-gray-300">
                      {formatTimestampOffset(currentFrame.timestamp_offset_ms)}
                    </span>
                  </div>
                  {currentFrame.width && currentFrame.height && (
                    <span className="text-xs text-gray-400">
                      {currentFrame.width} × {currentFrame.height}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Thumbnail strip for multi-frame navigation */}
            {frames.length > 1 && (
              <div className="flex gap-2 overflow-x-auto py-2 justify-center">
                {frames.map((frame, index) => (
                  <button
                    key={frame.id}
                    type="button"
                    onClick={() => setSelectedIndex(index)}
                    className={`flex-shrink-0 w-16 h-12 rounded overflow-hidden border-2 transition-all ${
                      index === selectedIndex
                        ? 'border-purple-500 ring-2 ring-purple-500/30'
                        : 'border-transparent opacity-60 hover:opacity-100'
                    }`}
                    aria-label={`Select frame ${frame.frame_number}`}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={getFrameImageUrl(frame.frame_number)}
                      alt={`Thumbnail ${frame.frame_number}`}
                      className="w-full h-full object-cover"
                    />
                  </button>
                ))}
              </div>
            )}

            {/* Keyboard hints */}
            <p className="text-xs text-center text-muted-foreground">
              Use ← → arrow keys to navigate, Escape to close
            </p>
          </>
        )}

        {/* Close button */}
        <div className="flex justify-end pt-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            <X className="w-4 h-4 mr-2" />
            Close
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
