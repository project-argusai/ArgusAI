/**
 * CameraPreviewModal component - full-screen camera preview with navigation
 */

'use client';

import { useEffect, useCallback } from 'react';
import Image from 'next/image';
import { X, ChevronLeft, ChevronRight, Video, PlayCircle, Loader2, AlertCircle } from 'lucide-react';
import type { ICamera } from '@/types/camera';
import { useCameraPreview, useAnalyzeCamera } from '@/lib/hooks/useCameraPreview';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

interface CameraPreviewModalProps {
  camera: ICamera | null;
  cameras: ICamera[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CameraPreviewModal({
  camera,
  cameras,
  open,
  onOpenChange,
}: CameraPreviewModalProps) {
  // Find current camera index in the list
  const currentIndex = camera ? cameras.findIndex((c) => c.id === camera.id) : -1;
  const hasMultipleCameras = cameras.length > 1;
  const canNavigatePrev = currentIndex > 0;
  const canNavigateNext = currentIndex < cameras.length - 1;

  // Fetch preview with auto-refresh (continues even in modal)
  const { data: previewUrl, isLoading, error } = useCameraPreview(
    camera?.id || '',
    open && !!camera?.is_enabled
  );

  // Manual analyze mutation
  const analyzeCamera = useAnalyzeCamera();

  const handleAnalyze = () => {
    if (camera) {
      analyzeCamera.mutate(camera.id);
    }
  };

  // Navigate to previous camera
  const navigatePrev = useCallback(() => {
    if (canNavigatePrev) {
      const prevCamera = cameras[currentIndex - 1];
      // Trigger navigation by changing the camera prop (handled by parent)
      // Since we can't modify parent state directly, we'll use a custom event
      const event = new CustomEvent('camera-modal-navigate', {
        detail: { cameraId: prevCamera.id },
      });
      window.dispatchEvent(event);
    }
  }, [canNavigatePrev, cameras, currentIndex]);

  // Navigate to next camera
  const navigateNext = useCallback(() => {
    if (canNavigateNext) {
      const nextCamera = cameras[currentIndex + 1];
      const event = new CustomEvent('camera-modal-navigate', {
        detail: { cameraId: nextCamera.id },
      });
      window.dispatchEvent(event);
    }
  }, [canNavigateNext, cameras, currentIndex]);

  // Keyboard navigation (Arrow Left/Right for prev/next, Escape to close)
  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        navigatePrev();
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        navigateNext();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, navigatePrev, navigateNext]);

  if (!camera) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl h-[90vh] flex flex-col p-0">
        {/* Header */}
        <DialogHeader className="px-6 py-4 border-b">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <Video className="w-6 h-6 text-blue-600" />
              <DialogTitle className="text-2xl">{camera.name}</DialogTitle>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onOpenChange(false)}
              className="h-8 w-8"
            >
              <X className="h-5 w-5" />
              <span className="sr-only">Close</span>
            </Button>
          </div>

          {/* Camera metadata */}
          <div className="flex items-center space-x-6 text-sm text-muted-foreground mt-2">
            <div>
              <span className="font-medium">Type:</span> {camera.type.toUpperCase()}
            </div>
            <div>
              <span className="font-medium">Frame Rate:</span> {camera.frame_rate} FPS
            </div>
            <div>
              <span className="font-medium">Status:</span>{' '}
              <span className={camera.is_enabled ? 'text-green-600' : 'text-gray-500'}>
                {camera.is_enabled ? 'Enabled' : 'Disabled'}
              </span>
            </div>
            <div>
              <span className="font-medium">Motion Detection:</span>{' '}
              <span className={camera.motion_enabled ? 'text-green-600' : 'text-gray-500'}>
                {camera.motion_enabled ? 'Active' : 'Inactive'}
              </span>
            </div>
          </div>
        </DialogHeader>

        {/* Preview area */}
        <div className="flex-1 relative bg-gray-100 overflow-hidden">
          {isLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-gray-200">
              <Loader2 className="w-12 h-12 text-blue-600 animate-spin" />
              <span className="sr-only">Loading preview...</span>
            </div>
          )}

          {error && !isLoading && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-red-50">
              <AlertCircle className="w-16 h-16 text-red-500 mb-4" />
              <p className="text-lg text-red-600 font-medium mb-2">Camera offline</p>
              <p className="text-sm text-red-500">Unable to fetch preview</p>
              <Button
                variant="outline"
                className="mt-4"
                onClick={() => window.location.reload()}
              >
                Retry
              </Button>
            </div>
          )}

          {previewUrl && !error && (
            <div className="absolute inset-0 flex items-center justify-center p-8">
              <div className="relative w-full h-full max-w-4xl max-h-full">
                <Image
                  src={previewUrl}
                  alt={`${camera.name} full preview`}
                  fill
                  className="object-contain"
                  unoptimized // Preview images change frequently
                  priority // Load immediately in modal
                />
              </div>
            </div>
          )}

          {!previewUrl && !isLoading && !error && (
            <div className="absolute inset-0 flex items-center justify-center">
              <Video className="w-24 h-24 text-gray-400" />
              <span className="sr-only">No preview available</span>
            </div>
          )}

          {/* Navigation buttons (only show if multiple cameras) */}
          {hasMultipleCameras && (
            <>
              <Button
                variant="secondary"
                size="icon"
                className="absolute left-4 top-1/2 -translate-y-1/2 h-12 w-12 rounded-full shadow-lg"
                onClick={navigatePrev}
                disabled={!canNavigatePrev}
              >
                <ChevronLeft className="h-6 w-6" />
                <span className="sr-only">Previous camera</span>
              </Button>
              <Button
                variant="secondary"
                size="icon"
                className="absolute right-4 top-1/2 -translate-y-1/2 h-12 w-12 rounded-full shadow-lg"
                onClick={navigateNext}
                disabled={!canNavigateNext}
              >
                <ChevronRight className="h-6 w-6" />
                <span className="sr-only">Next camera</span>
              </Button>
            </>
          )}

          {/* Camera indicator (e.g., "1 of 3") */}
          {hasMultipleCameras && (
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-black/70 text-white px-4 py-2 rounded-full text-sm">
              {currentIndex + 1} of {cameras.length}
            </div>
          )}
        </div>

        {/* Footer with actions */}
        <div className="px-6 py-4 border-t flex items-center justify-between">
          <div className="text-sm text-muted-foreground">
            {camera.is_enabled ? (
              <span className="text-green-600">● Live • Refreshing every 2s</span>
            ) : (
              <span className="text-gray-500">● Camera disabled</span>
            )}
          </div>

          <div className="flex items-center space-x-3">
            <Button
              variant="outline"
              onClick={handleAnalyze}
              disabled={analyzeCamera.isPending || !camera.is_enabled}
            >
              {analyzeCamera.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Analyzing...
                </>
              ) : (
                <>
                  <PlayCircle className="w-4 h-4 mr-2" />
                  Analyze Now
                </>
              )}
            </Button>
            <Button onClick={() => onOpenChange(false)}>Close</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
