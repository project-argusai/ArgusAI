/**
 * SourceTypeFilter - Tab filter for filtering cameras by source type
 *
 * Displays tabs for All, UniFi Protect, RTSP, and USB with camera counts.
 * Follows UX spec Section 10.6 for styling.
 */

'use client';

import { Shield, Camera, Usb } from 'lucide-react';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import type { CameraSourceType } from '@/types/camera';

export type SourceTypeFilterValue = CameraSourceType | 'all';

interface SourceTypeCounts {
  all: number;
  protect: number;
  rtsp: number;
  usb: number;
}

interface SourceTypeFilterProps {
  value: SourceTypeFilterValue;
  onChange: (value: SourceTypeFilterValue) => void;
  counts: SourceTypeCounts;
}

/**
 * Tab filter for camera source types
 * Shows counts for each category with icons
 */
export function SourceTypeFilter({ value, onChange, counts }: SourceTypeFilterProps) {
  return (
    <Tabs
      value={value}
      onValueChange={(v) => onChange(v as SourceTypeFilterValue)}
      className="w-full"
    >
      <TabsList className="overflow-x-auto overflow-y-hidden whitespace-nowrap scrollbar-hide">
        <TabsTrigger value="all" className="gap-1.5">
          All
          <span className="text-muted-foreground">({counts.all})</span>
        </TabsTrigger>
        <TabsTrigger value="protect" className="gap-1.5">
          <Shield className="h-3.5 w-3.5" aria-hidden="true" />
          UniFi Protect
          <span className="text-muted-foreground">({counts.protect})</span>
        </TabsTrigger>
        <TabsTrigger value="rtsp" className="gap-1.5">
          <Camera className="h-3.5 w-3.5" aria-hidden="true" />
          RTSP
          <span className="text-muted-foreground">({counts.rtsp})</span>
        </TabsTrigger>
        <TabsTrigger value="usb" className="gap-1.5">
          <Usb className="h-3.5 w-3.5" aria-hidden="true" />
          USB
          <span className="text-muted-foreground">({counts.usb})</span>
        </TabsTrigger>
      </TabsList>
    </Tabs>
  );
}

/**
 * Helper function to calculate source type counts from camera array
 */
export function calculateSourceTypeCounts(cameras: Array<{ source_type?: string }>): SourceTypeCounts {
  const counts: SourceTypeCounts = {
    all: cameras.length,
    protect: 0,
    rtsp: 0,
    usb: 0,
  };

  cameras.forEach((camera) => {
    const sourceType = camera.source_type || 'rtsp'; // Default to rtsp for legacy cameras
    if (sourceType === 'protect') counts.protect++;
    else if (sourceType === 'usb') counts.usb++;
    else counts.rtsp++; // Default unknown types to rtsp
  });

  return counts;
}
