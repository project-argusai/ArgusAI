/**
 * KeyFramesGallery component - displays key frames used for AI analysis
 * Story P3-7.5: Display Key Frames Gallery on Event Detail
 *
 * Shows a scrollable horizontal gallery of the frames that were sent to the AI
 * for multi-frame analysis, with timestamps displayed below each frame.
 */

'use client';

import { useState } from 'react';
import { Film, ChevronLeft, ChevronRight, X, ZoomIn } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

interface KeyFramesGalleryProps {
  /** Array of base64-encoded JPEG frame images */
  frames: string[];
  /** Array of timestamps in seconds for each frame */
  timestamps: number[];
}

/**
 * Format timestamp in seconds to MM:SS.ms format
 */
function formatTimestamp(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.round((seconds % 1) * 100);
  return `${mins}:${secs.toString().padStart(2, '0')}.${ms.toString().padStart(2, '0')}`;
}

export function KeyFramesGallery({ frames, timestamps }: KeyFramesGalleryProps) {
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);

  if (!frames || frames.length === 0) {
    return null;
  }

  const openLightbox = (index: number) => {
    setSelectedIndex(index);
    setLightboxOpen(true);
  };

  const navigateLightbox = (direction: 'prev' | 'next') => {
    if (direction === 'prev' && selectedIndex > 0) {
      setSelectedIndex(selectedIndex - 1);
    } else if (direction === 'next' && selectedIndex < frames.length - 1) {
      setSelectedIndex(selectedIndex + 1);
    }
  };

  return (
    <>
      {/* Gallery Section */}
      <div className="space-y-3 pt-4 border-t">
        <div className="flex items-center gap-2">
          <Film className="w-5 h-5 text-purple-500" />
          <h3 className="text-sm font-semibold text-gray-700">Key Frames Used for Analysis</h3>
          <span className="text-xs text-muted-foreground">
            ({frames.length} frame{frames.length !== 1 ? 's' : ''})
          </span>
        </div>

        {/* Horizontal scrollable gallery */}
        <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-thin scrollbar-thumb-gray-300 scrollbar-track-gray-100">
          {frames.map((frame, index) => (
            <button
              key={index}
              type="button"
              onClick={() => openLightbox(index)}
              className="group flex-shrink-0 flex flex-col rounded-lg border border-gray-200 overflow-hidden hover:border-purple-400 hover:shadow-md transition-all focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2"
              aria-label={`View frame ${index + 1} at ${formatTimestamp(timestamps[index] || 0)}`}
            >
              {/* Frame thumbnail */}
              <div className="relative w-32 h-24 bg-gray-100">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`data:image/jpeg;base64,${frame}`}
                  alt={`Frame ${index + 1}`}
                  className="w-full h-full object-cover group-hover:opacity-90 transition-opacity"
                />
                {/* Zoom overlay on hover */}
                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/20">
                  <ZoomIn className="w-6 h-6 text-white drop-shadow-lg" />
                </div>
              </div>

              {/* Timestamp label */}
              <div className="px-2 py-1.5 bg-gray-50 text-center">
                <p className="text-xs font-mono text-gray-600">
                  {formatTimestamp(timestamps[index] || 0)}
                </p>
                <p className="text-[10px] text-muted-foreground">
                  Frame {index + 1}
                </p>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Lightbox Modal for larger view */}
      <Dialog open={lightboxOpen} onOpenChange={setLightboxOpen}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Film className="w-5 h-5 text-purple-500" />
              Frame {selectedIndex + 1} of {frames.length}
              <span className="text-sm font-normal text-muted-foreground ml-2">
                @ {formatTimestamp(timestamps[selectedIndex] || 0)}
              </span>
            </DialogTitle>
          </DialogHeader>

          {/* Large frame view */}
          <div className="relative bg-black rounded-lg overflow-hidden">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`data:image/jpeg;base64,${frames[selectedIndex]}`}
              alt={`Frame ${selectedIndex + 1}`}
              className="w-full h-auto max-h-[60vh] object-contain mx-auto"
            />

            {/* Navigation arrows */}
            {frames.length > 1 && (
              <>
                <Button
                  variant="ghost"
                  size="icon"
                  className="absolute left-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white rounded-full"
                  onClick={() => navigateLightbox('prev')}
                  disabled={selectedIndex === 0}
                  aria-label="Previous frame"
                >
                  <ChevronLeft className="w-6 h-6" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="absolute right-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white rounded-full"
                  onClick={() => navigateLightbox('next')}
                  disabled={selectedIndex === frames.length - 1}
                  aria-label="Next frame"
                >
                  <ChevronRight className="w-6 h-6" />
                </Button>
              </>
            )}
          </div>

          {/* Thumbnail strip */}
          {frames.length > 1 && (
            <div className="flex gap-2 overflow-x-auto py-2 justify-center">
              {frames.map((frame, index) => (
                <button
                  key={index}
                  type="button"
                  onClick={() => setSelectedIndex(index)}
                  className={`flex-shrink-0 w-16 h-12 rounded overflow-hidden border-2 transition-all ${
                    index === selectedIndex
                      ? 'border-purple-500 ring-2 ring-purple-500/30'
                      : 'border-transparent opacity-60 hover:opacity-100'
                  }`}
                  aria-label={`Select frame ${index + 1}`}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={`data:image/jpeg;base64,${frame}`}
                    alt={`Thumbnail ${index + 1}`}
                    className="w-full h-full object-cover"
                  />
                </button>
              ))}
            </div>
          )}

          {/* Close button */}
          <div className="flex justify-end">
            <Button variant="outline" onClick={() => setLightboxOpen(false)}>
              <X className="w-4 h-4 mr-2" />
              Close
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
