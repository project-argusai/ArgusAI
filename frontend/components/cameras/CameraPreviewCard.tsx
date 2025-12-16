/**
 * CameraPreviewCard component - displays live camera preview with auto-refresh
 */

'use client';

import { memo, useState } from 'react';
import Image from 'next/image';
import { Video, Loader2, AlertCircle, PlayCircle } from 'lucide-react';
import type { ICamera } from '@/types/camera';
import { useCameraPreview, useAnalyzeCamera } from '@/lib/hooks/useCameraPreview';
import { Card, CardHeader, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

interface CameraPreviewCardProps {
  camera: ICamera;
  onClick: () => void;
}

/**
 * Determine connection status based on camera state and preview availability
 * Note: Using simplified logic since last_capture_at field not yet implemented in backend
 */
function getConnectionStatus(
  camera: ICamera,
  hasPreview: boolean,
  isLoading: boolean,
  hasError: boolean
): {
  status: 'connected' | 'connecting' | 'disconnected' | 'disabled';
  color: string;
  label: string;
} {
  // Camera manually disabled
  if (!camera.is_enabled) {
    return {
      status: 'disabled',
      color: 'bg-gray-400',
      label: 'Disabled',
    };
  }

  // Preview fetch error - camera disconnected
  if (hasError) {
    return {
      status: 'disconnected',
      color: 'bg-red-500',
      label: 'Disconnected',
    };
  }

  // Loading first preview - connecting
  if (isLoading && !hasPreview) {
    return {
      status: 'connecting',
      color: 'bg-yellow-400',
      label: 'Connecting',
    };
  }

  // Has preview - connected and streaming
  if (hasPreview) {
    return {
      status: 'connected',
      color: 'bg-green-500',
      label: 'Connected',
    };
  }

  // Default to connecting if enabled but no preview yet
  return {
    status: 'connecting',
    color: 'bg-yellow-400',
    label: 'Connecting',
  };
}

export const CameraPreviewCard = memo(function CameraPreviewCard({
  camera,
  onClick,
}: CameraPreviewCardProps) {
  const [imageError, setImageError] = useState(false);

  // Fetch preview with auto-refresh (only if enabled)
  const { data: previewUrl, isLoading, error } = useCameraPreview(
    camera.id,
    camera.is_enabled
  );

  // Determine connection status based on preview state
  const connectionStatus = getConnectionStatus(
    camera,
    !!previewUrl && !imageError,
    isLoading,
    !!error
  );

  // Manual analyze mutation
  const analyzeCamera = useAnalyzeCamera();

  const handleAnalyze = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent card click event
    analyzeCamera.mutate(camera.id);
  };

  // Format status text for footer
  const statusText = connectionStatus.status === 'connected'
    ? 'Live • Refreshing every 2s'
    : connectionStatus.label;

  return (
    <Card
      className="overflow-hidden cursor-pointer transition-all hover:shadow-lg hover:border-blue-300"
      onClick={onClick}
    >
      {/* Header with camera name and status */}
      <CardHeader className="flex flex-row items-center justify-between p-4 pb-2">
        <div className="flex items-center space-x-2">
          <Video className="w-5 h-5 text-blue-600" aria-hidden="true" />
          <h3 className="font-semibold text-base">{camera.name}</h3>
        </div>
        <div className="flex items-center space-x-2">
          <div
            className={`w-2 h-2 rounded-full ${connectionStatus.color}`}
            aria-hidden="true"
          />
          <span className="text-xs text-gray-600">{connectionStatus.label}</span>
        </div>
      </CardHeader>

      <CardContent className="p-4 pt-2">
        {/* Preview thumbnail with 16:9 aspect ratio */}
        <div className="relative w-full aspect-video bg-gray-100 rounded-lg overflow-hidden mb-3">
          {isLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-gray-200">
              <Loader2 className="w-8 h-8 text-blue-600 animate-spin" aria-hidden="true" />
              <span className="sr-only">Loading preview...</span>
            </div>
          )}

          {error && !isLoading && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-red-50 border-2 border-red-300" role="alert">
              <AlertCircle className="w-8 h-8 text-red-500 mb-2" aria-hidden="true" />
              <p className="text-sm text-red-600 font-medium">Camera offline</p>
              <Button
                variant="outline"
                size="sm"
                className="mt-2"
                onClick={(e) => {
                  e.stopPropagation();
                  window.location.reload();
                }}
                aria-label="Retry loading camera preview"
              >
                Retry
              </Button>
            </div>
          )}

          {previewUrl && !imageError && !error && (
            <Image
              src={previewUrl}
              alt={`${camera.name} preview`}
              fill
              className="object-cover transition-opacity duration-300"
              onError={() => setImageError(true)}
              unoptimized // Preview images change frequently
            />
          )}

          {(!previewUrl || imageError) && !isLoading && !error && (
            <div className="absolute inset-0 flex items-center justify-center bg-gray-200">
              <Video className="w-12 h-12 text-gray-400" aria-hidden="true" />
              <span className="sr-only">No preview available</span>
            </div>
          )}
        </div>

        {/* Footer with status and analyze button */}
        <div className="flex items-center justify-between">
          <div className="text-xs text-gray-600">
            {statusText}
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={handleAnalyze}
            disabled={analyzeCamera.isPending || !camera.is_enabled}
            className="flex items-center space-x-1"
            aria-label={`Analyze ${camera.name} now`}
          >
            {analyzeCamera.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
            ) : (
              <PlayCircle className="w-4 h-4" aria-hidden="true" />
            )}
            <span>Analyze Now</span>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
});
