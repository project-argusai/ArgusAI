/**
 * CameraGrid component - displays live camera previews in responsive grid
 */

'use client';

import { useState, useEffect, useMemo } from 'react';
import { Camera, AlertCircle } from 'lucide-react';
import { useCamerasQuery } from '@/hooks/useCamerasQuery';
import type { ICamera } from '@/types/camera';
import { CameraPreviewCard } from './CameraPreviewCard';
import { CameraPreviewModal } from './CameraPreviewModal';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import Link from 'next/link';

export function CameraGrid() {
  // Modal state
  const [selectedCamera, setSelectedCamera] = useState<ICamera | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  // Fetch all cameras using TanStack Query with shared cache (Story P6-1.4)
  const { data: cameras, isLoading, error, refetch } = useCamerasQuery();

  // Set up polling for live preview updates (refetch every 10 seconds)
  useEffect(() => {
    const interval = setInterval(() => {
      refetch();
    }, 10000);
    return () => clearInterval(interval);
  }, [refetch]);

  // Filter to only enabled cameras (memoized to prevent useEffect re-runs)
  const enabledCameras = useMemo(
    () => cameras?.filter((camera) => camera.is_enabled) || [],
    [cameras]
  );

  // Listen for camera navigation events from modal
  useEffect(() => {
    const handleNavigate = (e: Event) => {
      const customEvent = e as CustomEvent<{ cameraId: string }>;
      const camera = enabledCameras.find((c) => c.id === customEvent.detail.cameraId);
      if (camera) {
        setSelectedCamera(camera);
      }
    };

    window.addEventListener('camera-modal-navigate', handleNavigate);
    return () => window.removeEventListener('camera-modal-navigate', handleNavigate);
  }, [enabledCameras]);

  // Handle camera card click
  const handleCameraClick = (camera: ICamera) => {
    setSelectedCamera(camera);
    setModalOpen(true);
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Camera className="w-6 h-6 text-blue-600" />
            <h2 className="text-2xl font-bold">Live Cameras</h2>
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="p-4">
                <div className="w-full aspect-video bg-gray-200 rounded-lg mb-3" />
                <div className="h-4 bg-gray-200 rounded w-3/4" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Camera className="w-6 h-6 text-blue-600" />
            <h2 className="text-2xl font-bold">Live Cameras</h2>
          </div>
        </div>
        <Card className="border-red-200 bg-red-50">
          <CardContent className="p-6 flex flex-col items-center justify-center text-center">
            <AlertCircle className="w-12 h-12 text-red-500 mb-4" />
            <p className="text-red-700 font-medium mb-2">Failed to load cameras</p>
            <p className="text-red-600 text-sm mb-4">
              {error instanceof Error ? error.message : 'Unknown error occurred'}
            </p>
            <Button
              variant="outline"
              onClick={() => window.location.reload()}
            >
              Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Empty state - no cameras configured
  if (!cameras || cameras.length === 0) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Camera className="w-6 h-6 text-blue-600" />
            <h2 className="text-2xl font-bold">Live Cameras</h2>
          </div>
        </div>
        <Card>
          <CardContent className="p-12 flex flex-col items-center justify-center text-center">
            <Camera className="w-16 h-16 text-gray-400 mb-4" />
            <h3 className="text-xl font-semibold mb-2">No Cameras Configured</h3>
            <p className="text-muted-foreground mb-6 max-w-md">
              Get started by adding your first camera. You can connect RTSP network cameras or USB webcams.
            </p>
            <Link href="/cameras">
              <Button>
                <Camera className="w-4 h-4 mr-2" />
                Add Camera
              </Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Empty state - no enabled cameras
  if (enabledCameras.length === 0) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Camera className="w-6 h-6 text-blue-600" />
            <h2 className="text-2xl font-bold">Live Cameras</h2>
          </div>
          <span className="text-sm text-muted-foreground">
            {cameras.length} camera{cameras.length !== 1 ? 's' : ''} (all disabled)
          </span>
        </div>
        <Card>
          <CardContent className="p-12 flex flex-col items-center justify-center text-center">
            <Camera className="w-16 h-16 text-gray-400 mb-4" />
            <h3 className="text-xl font-semibold mb-2">All Cameras Disabled</h3>
            <p className="text-muted-foreground mb-6 max-w-md">
              You have {cameras.length} camera{cameras.length !== 1 ? 's' : ''} configured, but they are all disabled.
              Enable a camera to see live previews.
            </p>
            <Link href="/cameras">
              <Button variant="outline">
                Manage Cameras
              </Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Camera grid with previews
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Camera className="w-6 h-6 text-blue-600" />
          <h2 className="text-2xl font-bold">Live Cameras</h2>
        </div>
        <div className="flex items-center space-x-4">
          <span className="text-sm text-muted-foreground">
            {enabledCameras.length} active camera{enabledCameras.length !== 1 ? 's' : ''}
          </span>
          <Link href="/cameras">
            <Button variant="outline" size="sm">
              Manage
            </Button>
          </Link>
        </div>
      </div>

      {/* Responsive camera grid: 1 col (mobile), 2 cols (tablet), 3 cols (desktop) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {enabledCameras.map((camera) => (
          <CameraPreviewCard
            key={camera.id}
            camera={camera}
            onClick={() => handleCameraClick(camera)}
          />
        ))}
      </div>

      {/* Full-screen preview modal */}
      <CameraPreviewModal
        camera={selectedCamera}
        cameras={enabledCameras}
        open={modalOpen}
        onOpenChange={setModalOpen}
      />
    </div>
  );
}
