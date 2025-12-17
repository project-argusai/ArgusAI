/**
 * Camera list page
 * Displays grid of cameras with source type filtering and add/edit/delete actions
 * Phase 2: Supports RTSP, USB, and UniFi Protect camera sources
 */

'use client';

import { useState, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Video } from 'lucide-react';
import { useCamerasQuery, useCameraDelete } from '@/hooks/useCamerasQuery';
import { useToast } from '@/hooks/useToast';
import { CameraPreview } from '@/components/cameras/CameraPreview';
import { VirtualCameraList } from '@/components/cameras/VirtualCameraList';
import { SourceTypeFilter, calculateSourceTypeCounts, type SourceTypeFilterValue } from '@/components/cameras/SourceTypeFilter';
import { AddCameraDropdown } from '@/components/cameras/AddCameraDropdown';
import { CameraDiscovery } from '@/components/cameras/CameraDiscovery';
import { EmptyState } from '@/components/common/EmptyState';
import { Loading } from '@/components/common/Loading';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import type { ICamera } from '@/types/camera';

/**
 * Cameras page component
 */
export default function CamerasPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // TanStack Query hook for camera data with stale-while-revalidate caching (Story P6-1.4)
  const { data: cameras = [], isLoading: loading, error: queryError, refetch } = useCamerasQuery();
  const deleteMutation = useCameraDelete();
  const { showSuccess, showError } = useToast();

  // Convert query error to string for display
  const error = queryError ? (queryError instanceof Error ? queryError.message : 'Failed to fetch cameras') : null;

  // Get initial filter from URL query param, default to 'all'
  const initialFilter = (searchParams.get('source') as SourceTypeFilterValue) || 'all';
  const [sourceFilter, setSourceFilter] = useState<SourceTypeFilterValue>(initialFilter);

  // Delete confirmation state
  const [deleteDialog, setDeleteDialog] = useState<{
    open: boolean;
    camera: ICamera | null;
  }>({ open: false, camera: null });

  // Calculate source type counts from all cameras
  const sourceCounts = useMemo(() => calculateSourceTypeCounts(cameras), [cameras]);

  // Filter cameras based on selected source type
  const filteredCameras = useMemo(() => {
    if (sourceFilter === 'all') return cameras;
    return cameras.filter((camera) => {
      const cameraSourceType = camera.source_type || 'rtsp'; // Default to rtsp for legacy
      return cameraSourceType === sourceFilter;
    });
  }, [cameras, sourceFilter]);

  /**
   * Handle source filter change - update URL query param
   */
  const handleFilterChange = (value: SourceTypeFilterValue) => {
    setSourceFilter(value);
    // Update URL query param
    const params = new URLSearchParams(searchParams.toString());
    if (value === 'all') {
      params.delete('source');
    } else {
      params.set('source', value);
    }
    const newUrl = params.toString() ? `?${params.toString()}` : '/cameras';
    router.replace(newUrl, { scroll: false });
  };

  /**
   * Handle delete camera click
   */
  const handleDeleteClick = (camera: ICamera) => {
    setDeleteDialog({ open: true, camera });
  };

  /**
   * Confirm delete camera - uses TanStack Query mutation (Story P6-1.4)
   */
  const handleConfirmDelete = async () => {
    if (!deleteDialog.camera) return;

    try {
      await deleteMutation.mutateAsync(deleteDialog.camera.id);
      showSuccess('Camera deleted successfully');
      setDeleteDialog({ open: false, camera: null });
      // Note: Cache invalidation handled automatically by useCameraDelete mutation
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to delete camera');
    }
  };

  /**
   * Cancel delete
   */
  const handleCancelDelete = () => {
    setDeleteDialog({ open: false, camera: null });
  };

  /**
   * Navigate to add camera page (for empty state)
   */
  const handleAddCamera = () => {
    router.push('/cameras/new');
  };

  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl">
      {/* Page header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Cameras</h1>
          <p className="text-muted-foreground mt-2">
            Manage your camera feeds and configurations
          </p>
        </div>
        <AddCameraDropdown />
      </div>

      {/* ONVIF Camera Discovery (Story P5-2.3) */}
      {!loading && !error && (
        <div className="mb-6">
          <CameraDiscovery
            existingCameras={cameras}
            onDiscoveryComplete={(count) => {
              if (count > 0) {
                // Refresh cameras list when user adds a discovered camera
                // The refresh happens automatically when navigating back from /cameras/new
              }
            }}
          />
        </div>
      )}

      {/* Source type filter tabs */}
      {!loading && !error && cameras.length > 0 && (
        <div className="mb-6">
          <SourceTypeFilter
            value={sourceFilter}
            onChange={handleFilterChange}
            counts={sourceCounts}
          />
        </div>
      )}

      {/* Loading state */}
      {loading && <Loading message="Loading cameras..." />}

      {/* Error state */}
      {error && !loading && (
        <div className="bg-destructive/10 text-destructive px-4 py-3 rounded-lg">
          <p className="font-medium">Error loading cameras</p>
          <p className="text-sm mt-1">{error}</p>
          <button
            onClick={() => refetch()}
            className="mt-3 px-3 py-1.5 text-sm border rounded-md hover:bg-destructive/5"
          >
            Retry
          </button>
        </div>
      )}

      {/* Empty state - no cameras at all */}
      {!loading && !error && cameras.length === 0 && (
        <EmptyState
          icon={<Video className="h-16 w-16" />}
          title="No cameras configured yet"
          description="Add your first camera to start monitoring your space with AI-powered event detection."
          action={{
            label: 'Add Camera',
            onClick: handleAddCamera,
          }}
        />
      )}

      {/* Empty filtered state - cameras exist but none match filter */}
      {!loading && !error && cameras.length > 0 && filteredCameras.length === 0 && (
        <div className="text-center py-12">
          <Video className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
          <h3 className="text-lg font-medium mb-2">No {sourceFilter} cameras</h3>
          <p className="text-muted-foreground">
            {sourceFilter === 'protect'
              ? 'Configure UniFi Protect in Settings to auto-discover cameras.'
              : `No ${sourceFilter.toUpperCase()} cameras have been added yet.`}
          </p>
        </div>
      )}

      {/* Camera grid - uses virtual scrolling for 12+ cameras */}
      {!loading && !error && filteredCameras.length > 0 && (
        filteredCameras.length >= 12 ? (
          <VirtualCameraList
            cameras={filteredCameras}
            onDelete={handleDeleteClick}
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredCameras.map((camera) => (
              <CameraPreview
                key={camera.id}
                camera={camera}
                onDelete={handleDeleteClick}
              />
            ))}
          </div>
        )
      )}

      {/* Delete confirmation dialog */}
      <ConfirmDialog
        open={deleteDialog.open}
        title="Delete Camera"
        description={`Are you sure? This will delete all events from this camera.`}
        confirmText="Delete"
        cancelText="Cancel"
        destructive
        onConfirm={handleConfirmDelete}
        onCancel={handleCancelDelete}
      />
    </div>
  );
}
