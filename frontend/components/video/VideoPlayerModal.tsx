/**
 * Video Player Modal Component
 * Story P8-3.2: Displays full motion video with playback controls and download option
 */

'use client';

import { useState, useRef, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Download, Play, Pause, Volume2, VolumeX, Maximize, Loader2 } from 'lucide-react';
import { formatLocale } from '@/lib/datetime';

interface VideoPlayerModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  eventId: string;
  cameraName?: string;
  timestamp?: string;
}

export function VideoPlayerModal({
  open,
  onOpenChange,
  eventId,
  cameraName = 'Camera',
  timestamp,
}: VideoPlayerModalProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Reset state when modal opens
  useEffect(() => {
    if (open) {
      setIsPlaying(false);
      setIsLoading(true);
      setError(null);
    }
  }, [open, eventId]);

  const videoUrl = `/api/v1/events/${eventId}/video`;
  const downloadUrl = `/api/v1/events/${eventId}/video/download`;

  const handlePlayPause = () => {
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause();
      } else {
        videoRef.current.play();
      }
      setIsPlaying(!isPlaying);
    }
  };

  const handleMuteToggle = () => {
    if (videoRef.current) {
      videoRef.current.muted = !isMuted;
      setIsMuted(!isMuted);
    }
  };

  const handleFullscreen = () => {
    if (videoRef.current) {
      if (videoRef.current.requestFullscreen) {
        videoRef.current.requestFullscreen();
      }
    }
  };

  const handleDownload = () => {
    window.open(downloadUrl, '_blank');
  };

  const handleVideoLoad = () => {
    setIsLoading(false);
    setError(null);
  };

  const handleVideoError = () => {
    setIsLoading(false);
    setError('Failed to load video. The video may not be available.');
  };

  const handleVideoPlay = () => {
    setIsPlaying(true);
  };

  const handleVideoPause = () => {
    setIsPlaying(false);
  };

  const formattedTimestamp = timestamp
    ? formatLocale(timestamp)
    : undefined;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between">
            <span>{cameraName} - Motion Video</span>
            {formattedTimestamp && (
              <span className="text-sm font-normal text-muted-foreground">
                {formattedTimestamp}
              </span>
            )}
          </DialogTitle>
        </DialogHeader>

        <div className="relative bg-black rounded-lg overflow-hidden">
          {/* Loading state */}
          {isLoading && !error && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/50 z-10">
              <Loader2 className="h-8 w-8 animate-spin text-white" />
            </div>
          )}

          {/* Error state */}
          {error && (
            <div className="flex items-center justify-center h-64 bg-muted">
              <div className="text-center">
                <p className="text-muted-foreground">{error}</p>
              </div>
            </div>
          )}

          {/* Video element */}
          {!error && (
            <video
              ref={videoRef}
              src={videoUrl}
              className="w-full aspect-video"
              onLoadedData={handleVideoLoad}
              onError={handleVideoError}
              onPlay={handleVideoPlay}
              onPause={handleVideoPause}
              playsInline
              preload="metadata"
            >
              Your browser does not support the video tag.
            </video>
          )}
        </div>

        {/* Controls */}
        {!error && (
          <div className="flex items-center justify-between mt-2">
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="icon"
                onClick={handlePlayPause}
                disabled={isLoading}
              >
                {isPlaying ? (
                  <Pause className="h-4 w-4" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
              </Button>
              <Button
                variant="outline"
                size="icon"
                onClick={handleMuteToggle}
                disabled={isLoading}
              >
                {isMuted ? (
                  <VolumeX className="h-4 w-4" />
                ) : (
                  <Volume2 className="h-4 w-4" />
                )}
              </Button>
              <Button
                variant="outline"
                size="icon"
                onClick={handleFullscreen}
                disabled={isLoading}
              >
                <Maximize className="h-4 w-4" />
              </Button>
            </div>

            <Button
              variant="default"
              onClick={handleDownload}
              disabled={isLoading}
            >
              <Download className="h-4 w-4 mr-2" />
              Download
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
