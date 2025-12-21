/**
 * Discovered Camera Card Component
 * Story P2-2.2: Build Discovered Camera List UI with Enable/Disable
 * Story P2-2.3: Per-Camera Event Type Filtering
 * Story P2-2.4: Offline camera tooltip
 * Story P3-3.3: Analysis Mode Selector for Protect cameras
 *
 * Displays a single discovered camera from UniFi Protect controller with:
 * - Enable/disable checkbox
 * - Camera/doorbell icon based on type
 * - Camera name (bold) and type/model (muted)
 * - Online/offline status indicator with tooltip (Story P2-2.4 AC10)
 * - Configure Filters button with popover
 * - Filter badge showing active filters
 * - AI Mode button with analysis mode popover (Story P3-3.3)
 *
 * AC2: All required elements displayed
 * AC4: Disabled cameras at 50% opacity with "(Disabled)" label
 * AC5: Offline cameras show red status dot with "Offline" badge
 * AC8: Filter badge display (Story P2-2.3)
 * AC9: Filters button disabled when camera not enabled (Story P2-2.3)
 * AC10: Offline cameras show tooltip (Story P2-2.4)
 */

'use client';

import { Camera, Bell } from 'lucide-react';

import { cn } from '@/lib/utils';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { ProtectDiscoveredCamera } from '@/lib/api-client';
import type { AnalysisMode } from '@/types/camera';
import { EventTypeFilter, getFilterDisplayText } from './EventTypeFilter';
import { AnalysisModePopover } from './AnalysisModePopover';

export interface DiscoveredCameraCardProps {
  camera: ProtectDiscoveredCamera;
  controllerId: string;
  currentFilters?: string[];
  onToggleEnabled: (cameraId: string, enabled: boolean) => void;
  onFiltersUpdated?: () => void;
  isToggling?: boolean;
}

export function DiscoveredCameraCard({
  camera,
  controllerId,
  currentFilters,
  onToggleEnabled,
  onFiltersUpdated,
  isToggling = false,
}: DiscoveredCameraCardProps) {
  const handleCheckboxChange = (checked: boolean | 'indeterminate') => {
    if (checked !== 'indeterminate') {
      onToggleEnabled(camera.protect_camera_id, checked);
    }
  };

  // Determine icon based on camera type
  const CameraIcon = camera.is_doorbell ? Bell : Camera;

  // Get filter display text for badge (AC8)
  const filterText = camera.is_enabled_for_ai ? getFilterDisplayText(currentFilters) : null;

  return (
    <div
      className={cn(
        'flex items-center justify-between p-4 rounded-lg border bg-card transition-opacity',
        !camera.is_enabled_for_ai && 'opacity-50'
      )}
    >
      {/* Left side: Checkbox, Icon, Name, Type */}
      <div className="flex items-center gap-3">
        {/* Enable Checkbox (AC2) */}
        <Checkbox
          checked={camera.is_enabled_for_ai}
          onCheckedChange={handleCheckboxChange}
          disabled={isToggling}
          aria-label={`Enable ${camera.name} for AI analysis`}
        />

        {/* Camera Icon (AC2) - Doorbell or Camera based on type */}
        <div className="flex items-center justify-center w-8 h-8 rounded-full bg-muted">
          <CameraIcon className="h-4 w-4 text-muted-foreground" />
        </div>

        {/* Camera Info */}
        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            {/* Camera Name (bold) (AC2) */}
            <span className="font-medium">{camera.name}</span>

            {/* New Badge (Story P2-2.4 AC11) - Show for newly discovered cameras */}
            {camera.is_new && (
              <Badge variant="default" className="text-xs bg-blue-500 hover:bg-blue-600">
                New
              </Badge>
            )}

            {/* Disabled Label (AC4) */}
            {!camera.is_enabled_for_ai && !camera.is_new && (
              <span className="text-xs text-muted-foreground">(Disabled)</span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Camera Type/Model (muted) (AC2) */}
            <span className="text-sm text-muted-foreground">{camera.model}</span>

            {/* Filter Badge (AC8) - Only show when enabled */}
            {camera.is_enabled_for_ai && filterText && (
              <Badge variant="secondary" className="text-xs">
                {filterText}
              </Badge>
            )}
          </div>
        </div>
      </div>

      {/* Right side: Status, Configure Filters */}
      <div className="flex items-center gap-3">
        {/* Status Indicator (AC2, AC5) with tooltip for offline (AC10) */}
        <div className="flex items-center gap-2">
          {camera.is_online ? (
            // Online status - no tooltip needed
            <span
              className="h-2.5 w-2.5 rounded-full bg-green-500"
              aria-label="Online"
            />
          ) : (
            // Offline status - with tooltip (Story P2-2.4 AC10)
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-2 cursor-help">
                    <span
                      className="h-2.5 w-2.5 rounded-full bg-red-500"
                      aria-label="Offline"
                    />
                    <Badge variant="destructive" className="text-xs">
                      Offline
                    </Badge>
                  </div>
                </TooltipTrigger>
                <TooltipContent>
                  <p>Camera is offline in UniFi Protect</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>

        {/* Configure Filters Button with Popover (AC9 - disabled when not enabled) */}
        <EventTypeFilter
          camera={camera}
          controllerId={controllerId}
          currentFilters={currentFilters}
          onSave={onFiltersUpdated}
        />

        {/* AI Mode Button with Popover (Story P3-3.3) */}
        {camera.camera_id && (
          <AnalysisModePopover
            cameraId={camera.camera_id}
            currentMode={(camera.analysis_mode || 'single_frame') as AnalysisMode}
            isEnabled={camera.is_enabled_for_ai}
            onModeUpdated={onFiltersUpdated}
          />
        )}
      </div>
    </div>
  );
}
