/**
 * Add new camera page
 *
 * Story P5-2.3: Supports URL query params for pre-populated form from ONVIF discovery
 * - rtsp_url: Pre-populate RTSP URL field
 * - name: Pre-populate camera name field
 */

'use client';

import { useState, useMemo, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowLeft, Radar } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { CameraForm } from '@/components/cameras/CameraForm';
import { useToast } from '@/hooks/useToast';
import { apiClient, ApiError } from '@/lib/api-client';
import type { CameraFormValues } from '@/lib/validations/camera';
import type { ICamera } from '@/types/camera';

/**
 * Inner component that uses searchParams (must be wrapped in Suspense)
 */
function NewCameraPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { showSuccess, showError } = useToast();
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Extract query params for pre-population (Story P5-2.3)
  const prePopulatedData = useMemo(() => {
    const rtspUrl = searchParams.get('rtsp_url');
    const name = searchParams.get('name');

    // Only return data if we have at least rtsp_url
    if (rtspUrl) {
      return {
        rtsp_url: decodeURIComponent(rtspUrl),
        name: name ? decodeURIComponent(name) : undefined,
        fromDiscovery: true,
      };
    }
    return null;
  }, [searchParams]);

  // Clear query params after form loads (to avoid confusion on refresh)
  useEffect(() => {
    if (prePopulatedData) {
      // Replace URL without query params after a short delay
      const timeout = setTimeout(() => {
        router.replace('/cameras/new', { scroll: false });
      }, 100);
      return () => clearTimeout(timeout);
    }
  }, [prePopulatedData, router]);

  // Create initial data object for the form if pre-populated
  const initialData = useMemo((): ICamera | undefined => {
    if (!prePopulatedData) return undefined;

    // Create a minimal camera object with pre-populated values
    return {
      id: '', // Will be set on creation
      name: prePopulatedData.name || '',
      type: 'rtsp',
      rtsp_url: prePopulatedData.rtsp_url,
      frame_rate: 5,
      is_enabled: true,
      motion_enabled: true,
      motion_sensitivity: 'medium',
      motion_cooldown: 30,
      motion_algorithm: 'mog2',
      source_type: 'rtsp',
      analysis_mode: 'single_frame',
      homekit_stream_quality: 'medium', // Phase 7: HomeKit stream quality
      audio_enabled: false, // Phase 6: Audio settings
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
  }, [prePopulatedData]);

  /**
   * Handle form submission
   */
  const handleSubmit = async (data: CameraFormValues) => {
    setIsSubmitting(true);

    try {
      await apiClient.cameras.create(data);
      showSuccess('Camera added successfully!');
      // Small delay to let user see the success toast before redirecting
      setTimeout(() => {
        router.push('/cameras');
      }, 1000);
    } catch (err) {
      if (err instanceof ApiError) {
        showError(err.message);
      } else {
        showError('Failed to add camera');
      }
      setIsSubmitting(false);
    }
  };

  /**
   * Handle cancel
   */
  const handleCancel = () => {
    router.push('/cameras');
  };

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

      {/* Page header */}
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <h1 className="text-3xl font-bold tracking-tight">Add Camera</h1>
          {prePopulatedData?.fromDiscovery && (
            <Badge variant="secondary" className="flex items-center gap-1">
              <Radar className="h-3 w-3" />
              From Discovery
            </Badge>
          )}
        </div>
        <p className="text-muted-foreground mt-2">
          {prePopulatedData?.fromDiscovery
            ? 'Camera details have been pre-filled from ONVIF discovery. Review and customize as needed.'
            : 'Configure a new camera for event monitoring'}
        </p>
      </div>

      {/* Form */}
      <div className="bg-card border rounded-lg p-6">
        <CameraForm
          initialData={initialData}
          onSubmit={handleSubmit}
          onCancel={handleCancel}
          isSubmitting={isSubmitting}
        />
      </div>
    </div>
  );
}

/**
 * New camera page component
 * Wraps content in Suspense for useSearchParams
 */
export default function NewCameraPage() {
  return (
    <Suspense fallback={
      <div className="container mx-auto px-4 py-8 max-w-2xl">
        <div className="animate-pulse">
          <div className="h-8 w-32 bg-muted rounded mb-6" />
          <div className="h-10 w-48 bg-muted rounded mb-2" />
          <div className="h-4 w-64 bg-muted rounded mb-8" />
          <div className="bg-card border rounded-lg p-6">
            <div className="space-y-4">
              <div className="h-10 bg-muted rounded" />
              <div className="h-10 bg-muted rounded" />
              <div className="h-10 bg-muted rounded" />
            </div>
          </div>
        </div>
      </div>
    }>
      <NewCameraPageContent />
    </Suspense>
  );
}
