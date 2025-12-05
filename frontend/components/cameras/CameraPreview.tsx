/**
 * Camera preview card component
 * Displays camera info with source badge, status indicator, and action buttons
 * Phase 2: Supports RTSP, USB, and UniFi Protect cameras with source-specific features
 */

'use client';

import Link from 'next/link';
import { Edit, Trash2, Shield, Camera, Usb, Settings } from 'lucide-react';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { CameraStatus } from './CameraStatus';
import type { ICamera, CameraSourceType } from '@/types/camera';
import { format } from 'date-fns';

interface CameraPreviewProps {
  /**
   * Camera object
   */
  camera: ICamera;
  /**
   * Delete button click handler
   */
  onDelete: (camera: ICamera) => void;
}

/**
 * Source type badge configuration
 */
const SOURCE_CONFIG: Record<CameraSourceType, { icon: typeof Shield; label: string; bgColor: string; textColor: string }> = {
  protect: { icon: Shield, label: 'Protect', bgColor: 'bg-cyan-50', textColor: 'text-cyan-600' },
  rtsp: { icon: Camera, label: 'RTSP', bgColor: 'bg-blue-50', textColor: 'text-blue-600' },
  usb: { icon: Usb, label: 'USB', bgColor: 'bg-purple-50', textColor: 'text-purple-600' },
};

/**
 * Camera preview card
 * Shows camera name, source type badge, status, and action buttons
 */
export function CameraPreview({ camera, onDelete }: CameraPreviewProps) {
  const sourceType = (camera.source_type || camera.type || 'rtsp') as CameraSourceType;
  const sourceConfig = SOURCE_CONFIG[sourceType] || SOURCE_CONFIG.rtsp;
  const SourceIcon = sourceConfig.icon;
  const isProtect = sourceType === 'protect';

  return (
    <Card className="hover:shadow-lg transition-shadow">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${sourceConfig.bgColor}`}>
              <SourceIcon className={`h-5 w-5 ${sourceConfig.textColor}`} />
            </div>
            <div>
              <h3 className="font-semibold text-lg">{camera.name}</h3>
              {/* Source type badge with optional model info for Protect */}
              <div className="flex items-center gap-2 mt-0.5">
                <span className={`text-xs font-medium ${sourceConfig.textColor}`}>
                  {sourceConfig.label}
                </span>
                {isProtect && camera.protect_camera_type && (
                  <span className="text-xs text-muted-foreground">
                    {camera.protect_camera_type}
                  </span>
                )}
                {!isProtect && (
                  <span className="text-xs text-muted-foreground">
                    {camera.type === 'rtsp' ? 'Camera' : 'Camera'}
                  </span>
                )}
              </div>
            </div>
          </div>
          <CameraStatus isEnabled={camera.is_enabled} />
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Camera details */}
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <span className="text-muted-foreground">Frame Rate:</span>
            <span className="ml-2 font-medium">{camera.frame_rate} FPS</span>
          </div>
          <div>
            <span className="text-muted-foreground">Sensitivity:</span>
            <span className="ml-2 font-medium capitalize">
              {camera.motion_sensitivity}
            </span>
          </div>
        </div>

        {/* Protect-specific info: doorbell indicator */}
        {isProtect && camera.is_doorbell && (
          <div className="text-xs bg-amber-50 text-amber-700 px-2 py-1 rounded-md inline-flex items-center gap-1">
            Doorbell
          </div>
        )}

        {/* Updated timestamp */}
        <div className="text-xs text-muted-foreground">
          Updated: {format(new Date(camera.updated_at), 'MMM d, yyyy h:mm a')}
        </div>

        {/* Action buttons */}
        <div className="flex gap-2 pt-2">
          {isProtect ? (
            // Protect cameras: Configure link instead of Edit
            <Button
              asChild
              variant="outline"
              size="sm"
              className="flex-1"
            >
              <Link href="/settings?tab=protect">
                <Settings className="h-4 w-4 mr-2" />
                Configure
              </Link>
            </Button>
          ) : (
            // RTSP/USB cameras: Edit link
            <Button
              asChild
              variant="outline"
              size="sm"
              className="flex-1"
            >
              <Link href={`/cameras/${camera.id}`}>
                <Edit className="h-4 w-4 mr-2" />
                Edit
              </Link>
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => onDelete(camera)}
            className="text-destructive hover:text-destructive"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
