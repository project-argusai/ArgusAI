/**
 * DiscoveredCameraCard - Card component for displaying a discovered ONVIF camera
 *
 * Story P5-2.3: Build Camera Discovery UI with Add Action
 * Story P5-2.4: Add Test Connection button
 *
 * Shows camera details (name, manufacturer, model, IP) and stream profiles.
 * Provides "Test" and "Add" buttons for RTSP connection verification.
 */

'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Plus, Camera, CheckCircle, Loader2, AlertCircle, ChevronDown, ChevronUp, Play, XCircle, Key } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { IDiscoveredCameraDetails, IStreamProfile, ITestConnectionResponse } from '@/types/discovery';
import type { ICamera } from '@/types/camera';
import { apiClient, ApiError } from '@/lib/api-client';

interface DiscoveredCameraCardProps {
  /** Camera details from ONVIF discovery */
  camera: IDiscoveredCameraDetails;
  /** List of existing cameras to check for duplicates */
  existingCameras?: ICamera[];
  /** Whether device details are loading */
  isLoadingDetails?: boolean;
  /** Error message if device query failed */
  detailsError?: string | null;
}

/**
 * Check if a discovered camera is already added to ArgusAI
 * Compares IP address and port from existing RTSP URLs
 */
function isAlreadyAdded(
  discoveredIp: string,
  discoveredPort: number,
  existingCameras: ICamera[]
): boolean {
  return existingCameras.some((cam) => {
    if (cam.rtsp_url) {
      try {
        const url = new URL(cam.rtsp_url);
        const hostname = url.hostname;
        // Compare IP and port
        return hostname === discoveredIp;
      } catch {
        return false;
      }
    }
    return false;
  });
}

/**
 * Get the best profile from available stream profiles
 * Returns the profile with highest resolution
 */
function getBestProfile(profiles: IStreamProfile[]): IStreamProfile | null {
  if (profiles.length === 0) return null;
  return profiles.reduce((best, current) => {
    const bestPixels = best.width * best.height;
    const currentPixels = current.width * current.height;
    return currentPixels > bestPixels ? current : best;
  });
}

/**
 * Card component for a discovered ONVIF camera
 */
export function DiscoveredCameraCard({
  camera,
  existingCameras = [],
  isLoadingDetails = false,
  detailsError,
}: DiscoveredCameraCardProps) {
  const router = useRouter();
  const [selectedProfileToken, setSelectedProfileToken] = useState<string | null>(null);
  const [showProfiles, setShowProfiles] = useState(false);

  // Test connection state (Story P5-2.4)
  const [showCredentials, setShowCredentials] = useState(false);
  const [testUsername, setTestUsername] = useState('');
  const [testPassword, setTestPassword] = useState('');
  const [testState, setTestState] = useState<{
    loading: boolean;
    result: ITestConnectionResponse | null;
  }>({ loading: false, result: null });

  const alreadyAdded = isAlreadyAdded(camera.ip_address, camera.port, existingCameras);
  const bestProfile = getBestProfile(camera.profiles);

  // Get selected profile or default to best/primary
  const selectedProfile = selectedProfileToken
    ? camera.profiles.find((p) => p.token === selectedProfileToken)
    : bestProfile;

  const rtspUrl = selectedProfile?.rtsp_url || camera.primary_rtsp_url;

  /**
   * Handle add camera click - navigate to new camera form with pre-populated data
   */
  const handleAddCamera = () => {
    const params = new URLSearchParams({
      rtsp_url: rtspUrl,
      name: camera.device_info.name || `${camera.device_info.manufacturer} ${camera.device_info.model}`,
    });
    // Include credentials if provided during test
    if (testUsername) {
      params.append('username', testUsername);
    }
    router.push(`/cameras/new?${params.toString()}`);
  };

  /**
   * Handle test connection click (Story P5-2.4)
   */
  const handleTestConnection = async () => {
    setTestState({ loading: true, result: null });

    try {
      const result = await apiClient.discovery.testConnection(
        rtspUrl,
        testUsername || null,
        testPassword || null
      );

      setTestState({ loading: false, result });

      // If auth failed and no credentials shown, suggest entering them
      if (!result.success && result.error?.includes('Authentication') && !showCredentials) {
        setShowCredentials(true);
      }
    } catch (err) {
      setTestState({
        loading: false,
        result: {
          success: false,
          error: err instanceof ApiError ? err.message : 'Connection test failed',
        },
      });
    }
  };

  return (
    <div className="border rounded-lg p-4 bg-card hover:border-primary/50 transition-colors">
      {/* Header with camera icon and name */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-start gap-3">
          <div className="p-2 rounded-lg bg-primary/10 text-primary">
            <Camera className="h-5 w-5" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-medium truncate">
              {camera.device_info.name || camera.device_info.model}
            </h3>
            <p className="text-sm text-muted-foreground">
              {camera.device_info.manufacturer}
            </p>
          </div>
        </div>

        {/* Already added badge */}
        {alreadyAdded && (
          <Badge variant="secondary" className="flex items-center gap-1 shrink-0">
            <CheckCircle className="h-3 w-3" />
            Already Added
          </Badge>
        )}
      </div>

      {/* Loading state for details */}
      {isLoadingDetails && (
        <div className="flex items-center gap-2 text-muted-foreground text-sm py-4">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading camera details...
        </div>
      )}

      {/* Error state */}
      {detailsError && (
        <div className="flex items-start gap-2 text-destructive text-sm py-2">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          <span>{detailsError}</span>
        </div>
      )}

      {/* Camera details */}
      {!isLoadingDetails && !detailsError && (
        <>
          {/* IP and model info */}
          <div className="space-y-1 text-sm mb-3">
            <div className="flex justify-between">
              <span className="text-muted-foreground">IP Address:</span>
              <span className="font-mono">{camera.ip_address}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Model:</span>
              <span className="truncate ml-2">{camera.device_info.model}</span>
            </div>
            {camera.device_info.firmware_version && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Firmware:</span>
                <span className="truncate ml-2">{camera.device_info.firmware_version}</span>
              </div>
            )}
          </div>

          {/* Best profile info */}
          {bestProfile && (
            <div className="mb-3">
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="font-mono">
                  {bestProfile.resolution}
                </Badge>
                <Badge variant="outline" className="font-mono">
                  {bestProfile.fps} FPS
                </Badge>
                {bestProfile.encoding && (
                  <Badge variant="outline">{bestProfile.encoding}</Badge>
                )}
              </div>
            </div>
          )}

          {/* Profile selector (expandable) */}
          {camera.profiles.length > 1 && (
            <div className="mb-3">
              <button
                type="button"
                onClick={() => setShowProfiles(!showProfiles)}
                className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
                aria-expanded={showProfiles}
              >
                {showProfiles ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
                {camera.profiles.length} stream profiles available
              </button>

              {showProfiles && (
                <div className="mt-2">
                  <Select
                    value={selectedProfileToken || bestProfile?.token || ''}
                    onValueChange={setSelectedProfileToken}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Select stream profile" />
                    </SelectTrigger>
                    <SelectContent>
                      {camera.profiles.map((profile) => (
                        <SelectItem key={profile.token} value={profile.token}>
                          <span className="flex items-center gap-2">
                            {profile.name} - {profile.resolution} @ {profile.fps}fps
                            {profile.encoding && ` (${profile.encoding})`}
                          </span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>
          )}

          {/* Auth required indicator / Credentials toggle */}
          {(camera.requires_auth || showCredentials) && (
            <div className="mb-3">
              {!showCredentials && (
                <button
                  type="button"
                  onClick={() => setShowCredentials(true)}
                  className="flex items-center gap-2 text-amber-600 text-sm hover:text-amber-700 transition-colors rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-1"
                >
                  <Key className="h-4 w-4" />
                  <span>Credentials may be required - click to enter</span>
                </button>
              )}

              {showCredentials && (
                <div className="space-y-2 p-3 bg-muted/50 rounded-md">
                  <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
                    <Key className="h-4 w-4" />
                    <span>RTSP Credentials</span>
                  </div>
                  <Input
                    type="text"
                    placeholder="Username"
                    value={testUsername}
                    onChange={(e) => setTestUsername(e.target.value)}
                    className="h-8 text-sm"
                  />
                  <Input
                    type="password"
                    placeholder="Password"
                    value={testPassword}
                    onChange={(e) => setTestPassword(e.target.value)}
                    className="h-8 text-sm"
                  />
                </div>
              )}
            </div>
          )}

          {/* Test Result (Story P5-2.4) */}
          {testState.result && (
            <div
              className={`mb-3 p-3 rounded-md text-sm ${
                testState.result.success
                  ? 'bg-green-50 border border-green-200 dark:bg-green-950 dark:border-green-800'
                  : 'bg-red-50 border border-red-200 dark:bg-red-950 dark:border-red-800'
              }`}
            >
              <div className="flex items-start gap-2">
                {testState.result.success ? (
                  <CheckCircle className="h-4 w-4 text-green-600 dark:text-green-400 flex-shrink-0 mt-0.5" />
                ) : (
                  <XCircle className="h-4 w-4 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                )}
                <div className="flex-1">
                  {testState.result.success ? (
                    <>
                      <span className="font-medium text-green-900 dark:text-green-100">
                        Connected: {testState.result.resolution}
                      </span>
                      <span className="text-green-700 dark:text-green-300">
                        {' '}@ {testState.result.fps}fps
                        {testState.result.codec && ` (${testState.result.codec})`}
                      </span>
                      {testState.result.latency_ms && (
                        <span className="text-green-600 dark:text-green-400 text-xs ml-1">
                          ({testState.result.latency_ms}ms)
                        </span>
                      )}
                    </>
                  ) : (
                    <span className="text-red-900 dark:text-red-100">
                      {testState.result.error}
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Action buttons - Test and Add */}
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleTestConnection}
              disabled={testState.loading}
              className="flex-1"
            >
              {testState.loading ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Play className="h-4 w-4 mr-2" />
              )}
              Test
            </Button>
            <Button
              onClick={handleAddCamera}
              disabled={alreadyAdded}
              className="flex-1"
              variant={alreadyAdded ? 'secondary' : 'default'}
            >
              <Plus className="h-4 w-4 mr-2" />
              {alreadyAdded ? 'Added' : 'Add'}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
