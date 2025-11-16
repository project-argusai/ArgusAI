/**
 * Edit camera page
 */

'use client';

import { use, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { CameraForm } from '@/components/cameras/CameraForm';
import { Loading } from '@/components/common/Loading';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { useCameraDetail } from '@/hooks/useCameraDetail';
import { useToast } from '@/hooks/useToast';
import { apiClient, ApiError } from '@/lib/api-client';
import type { CameraFormValues } from '@/lib/validations/camera';

interface EditCameraPageProps {
  params: Promise<{
    id: string;
  }>;
}

/**
 * Edit camera page component
 */
export default function EditCameraPage({ params }: EditCameraPageProps) {
  // Unwrap params Promise (Next.js 15+ requirement)
  const { id } = use(params);

  const router = useRouter();
  const { showSuccess, showError } = useToast();
  const { camera, loading, error } = useCameraDetail(id);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [deleteDialog, setDeleteDialog] = useState(false);

  /**
   * Handle form submission
   */
  const handleSubmit = async (data: CameraFormValues) => {
    if (!camera) return;

    setIsSubmitting(true);

    try {
      await apiClient.cameras.update(camera.id, data);
      showSuccess('Camera updated successfully');
      router.push('/cameras');
    } catch (err) {
      if (err instanceof ApiError) {
        showError(err.message);
      } else {
        showError('Failed to update camera');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  /**
   * Handle cancel
   */
  const handleCancel = () => {
    router.push('/cameras');
  };

  /**
   * Handle delete confirmation
   */
  const handleConfirmDelete = async () => {
    if (!camera) return;

    try {
      await apiClient.cameras.delete(camera.id);
      showSuccess('Camera deleted successfully');
      router.push('/cameras');
    } catch (err) {
      if (err instanceof ApiError) {
        showError(err.message);
      } else {
        showError('Failed to delete camera');
      }
      setDeleteDialog(false);
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-2xl">
        <Loading message="Loading camera..." />
      </div>
    );
  }

  // Error state (404 or other error)
  if (error || !camera) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-2xl">
        <div className="bg-destructive/10 text-destructive px-4 py-3 rounded-lg">
          <p className="font-medium">Camera not found</p>
          <p className="text-sm mt-1">
            {error || 'The camera you are looking for does not exist.'}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => router.push('/cameras')}
            className="mt-3"
          >
            Back to Cameras
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-2xl">
      {/* Back button */}
      <Button
        variant="ghost"
        size="sm"
        onClick={handleCancel}
        className="mb-6"
      >
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back to Cameras
      </Button>

      {/* Page header with delete button */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Edit Camera</h1>
          <p className="text-muted-foreground mt-2">
            Update camera configuration and settings
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setDeleteDialog(true)}
          className="text-destructive hover:text-destructive"
        >
          <Trash2 className="h-4 w-4 mr-2" />
          Delete
        </Button>
      </div>

      {/* Form */}
      <div className="bg-card border rounded-lg p-6">
        <CameraForm
          initialData={camera}
          onSubmit={handleSubmit}
          onCancel={handleCancel}
          isSubmitting={isSubmitting}
        />
      </div>

      {/* Delete confirmation dialog */}
      <ConfirmDialog
        open={deleteDialog}
        title="Delete Camera"
        description="Are you sure? This will delete all events from this camera."
        confirmText="Delete"
        cancelText="Cancel"
        destructive
        onConfirm={handleConfirmDelete}
        onCancel={() => setDeleteDialog(false)}
      />
    </div>
  );
}
