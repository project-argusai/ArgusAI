/**
 * LiveStreamModal Component (Story P16-2.4)
 * Modal dialog for displaying live camera streams
 * Features:
 * - Opens with LiveStreamPlayer component
 * - Shows camera name in header
 * - Closeable with X button or Escape key
 * - Handles offline/unavailable streams with fallback message
 */

'use client';

import { Video } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { LiveStreamPlayer } from './LiveStreamPlayer';
import type { StreamQuality } from '@/types/camera';

interface LiveStreamModalProps {
  /**
   * Whether the modal is open
   */
  open: boolean;
  /**
   * Callback when modal should close
   */
  onOpenChange: (open: boolean) => void;
  /**
   * Camera ID to stream
   */
  cameraId: string;
  /**
   * Camera name for header display
   */
  cameraName: string;
  /**
   * Initial quality level (default: medium)
   */
  initialQuality?: StreamQuality;
}

/**
 * LiveStreamModal - Dialog wrapper for LiveStreamPlayer
 * Provides a modal interface for viewing live camera streams
 */
export function LiveStreamModal({
  open,
  onOpenChange,
  cameraId,
  cameraName,
  initialQuality = 'medium',
}: LiveStreamModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-4xl w-[95vw] p-0 gap-0 overflow-hidden"
        showCloseButton={true}
      >
        <DialogHeader className="px-4 py-3 border-b">
          <DialogTitle className="flex items-center gap-2">
            <Video className="h-5 w-5 text-primary" />
            <span>Live View - {cameraName}</span>
          </DialogTitle>
        </DialogHeader>

        <div className="relative">
          <LiveStreamPlayer
            cameraId={cameraId}
            cameraName={cameraName}
            initialQuality={initialQuality}
            aspectRatio="aspect-video"
            showControls={true}
            className="rounded-none"
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
