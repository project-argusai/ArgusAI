'use client';

/**
 * HomekitSettings component (Story P4-6.1, P5-1.8, P7-1.1, P7-1.2, P7-3.3)
 *
 * Settings UI for HomeKit integration with enable toggle, pairing status,
 * pairings list, and reset functionality.
 *
 * Story P5-1.8 additions:
 * - Display list of paired devices (AC3)
 * - Remove individual pairings (AC4)
 * - Show count of paired users (AC5)
 *
 * Story P7-1.1 additions:
 * - Diagnostics panel for troubleshooting (AC6)
 *
 * Story P7-1.2 additions:
 * - Connectivity test button (AC6)
 *
 * Story P7-3.3 additions:
 * - Stream test button for camera diagnostics (AC4)
 */
import React, { useState } from 'react';
import {
  useHomekitStatus,
  useHomekitToggle,
  useHomekitReset,
  useHomekitPairings,
  useHomekitRemovePairing,
  useHomekitTestConnectivity,
  useHomekitTestStream,
  type HomekitPairing,
  type HomekitConnectivityTestResponse,
  type HomekitStreamTestResponse,
} from '@/hooks/useHomekitStatus';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Loader2, AlertCircle, Check, X, RotateCcw, Smartphone, Trash2, Users, Shield, User, Wifi, WifiOff, Network, Video, Play } from 'lucide-react';
import { HomeKitDiagnostics } from './HomeKitDiagnostics';

/**
 * ConnectivityTest subcomponent (Story P7-1.2 AC6)
 *
 * Button to run connectivity test and display results.
 */
function ConnectivityTest({ enabled }: { enabled: boolean }) {
  const testMutation = useHomekitTestConnectivity();
  const [showResults, setShowResults] = useState(false);

  const handleTest = async () => {
    try {
      await testMutation.mutateAsync();
      setShowResults(true);
    } catch (err) {
      console.error('Connectivity test failed:', err);
    }
  };

  const results = testMutation.data;

  return (
    <div className="space-y-3">
      <Button
        variant="outline"
        onClick={handleTest}
        disabled={!enabled || testMutation.isPending}
        className="w-full"
      >
        {testMutation.isPending ? (
          <>
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            Testing connectivity... (3-5s)
          </>
        ) : (
          <>
            <Network className="h-4 w-4 mr-2" />
            Test Connectivity
          </>
        )}
      </Button>

      {showResults && results && (
        <div className="border rounded-lg p-4 space-y-3 bg-muted/30">
          <div className="flex items-center justify-between">
            <h5 className="font-medium">Connectivity Test Results</h5>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowResults(false)}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            {/* mDNS Status */}
            <div className="flex items-center gap-2">
              {results.mdns_visible ? (
                <Wifi className="h-4 w-4 text-green-500" />
              ) : (
                <WifiOff className="h-4 w-4 text-red-500" />
              )}
              <span>mDNS</span>
              <Badge variant={results.mdns_visible ? "default" : "destructive"} className="ml-auto">
                {results.mdns_visible ? 'Visible' : 'Not Found'}
              </Badge>
            </div>

            {/* Port Status */}
            <div className="flex items-center gap-2">
              {results.port_accessible ? (
                <Check className="h-4 w-4 text-green-500" />
              ) : (
                <X className="h-4 w-4 text-red-500" />
              )}
              <span>Port {results.network_binding?.port || 51826}</span>
              <Badge variant={results.port_accessible ? "default" : "destructive"} className="ml-auto">
                {results.port_accessible ? 'Open' : 'Blocked'}
              </Badge>
            </div>
          </div>

          {results.discovered_as && (
            <div className="text-xs text-muted-foreground">
              Discovered as: <code className="bg-muted px-1 rounded">{results.discovered_as}</code>
            </div>
          )}

          {results.firewall_issues.length > 0 && (
            <Alert variant="destructive" className="py-2">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle className="text-sm">Firewall Issues</AlertTitle>
              <AlertDescription>
                <ul className="list-disc list-inside text-xs">
                  {results.firewall_issues.map((issue, i) => (
                    <li key={i}>{issue}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}

          {results.recommendations.length > 0 && (
            <div className="text-xs space-y-1">
              <span className="font-medium">Recommendations:</span>
              <ul className="list-disc list-inside text-muted-foreground">
                {results.recommendations.map((rec, i) => (
                  <li key={i}>{rec}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="text-xs text-muted-foreground text-right">
            Test completed in {results.test_duration_ms}ms
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * StreamTest subcomponent (Story P7-3.3 AC4)
 *
 * Button to run camera stream test and display results including
 * RTSP accessibility, ffmpeg compatibility, and sanitized command.
 */
function StreamTest({ cameraId, cameraName, enabled }: {
  cameraId: string;
  cameraName: string;
  enabled: boolean;
}) {
  const testMutation = useHomekitTestStream();
  const [showResults, setShowResults] = useState(false);

  const handleTest = async () => {
    try {
      await testMutation.mutateAsync(cameraId);
      setShowResults(true);
    } catch (err) {
      console.error('Stream test failed:', err);
      setShowResults(true);
    }
  };

  const results = testMutation.data;

  return (
    <div className="space-y-3">
      <Button
        variant="outline"
        size="sm"
        onClick={handleTest}
        disabled={!enabled || testMutation.isPending}
      >
        {testMutation.isPending ? (
          <>
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            Testing stream...
          </>
        ) : (
          <>
            <Play className="h-4 w-4 mr-2" />
            Test Stream
          </>
        )}
      </Button>

      {showResults && results && (
        <div className="border rounded-lg p-3 space-y-2 bg-muted/30 text-sm">
          <div className="flex items-center justify-between">
            <h6 className="font-medium">Stream Test: {cameraName}</h6>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowResults(false)}
              className="h-6 w-6 p-0"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>

          {/* Overall Status */}
          <div className="flex items-center gap-2">
            {results.success ? (
              <>
                <Check className="h-4 w-4 text-green-500" />
                <span className="text-green-600">Stream test passed</span>
              </>
            ) : (
              <>
                <X className="h-4 w-4 text-red-500" />
                <span className="text-red-600">Stream test failed</span>
              </>
            )}
          </div>

          {/* Test Results Grid */}
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="flex items-center gap-1">
              {results.rtsp_accessible ? (
                <Check className="h-3 w-3 text-green-500" />
              ) : (
                <X className="h-3 w-3 text-red-500" />
              )}
              <span>RTSP</span>
              <Badge variant={results.rtsp_accessible ? "default" : "destructive"} className="ml-auto text-xs">
                {results.rtsp_accessible ? 'Accessible' : 'Failed'}
              </Badge>
            </div>

            <div className="flex items-center gap-1">
              {results.ffmpeg_compatible ? (
                <Check className="h-3 w-3 text-green-500" />
              ) : (
                <X className="h-3 w-3 text-red-500" />
              )}
              <span>ffmpeg</span>
              <Badge variant={results.ffmpeg_compatible ? "default" : "destructive"} className="ml-auto text-xs">
                {results.ffmpeg_compatible ? 'Ready' : 'Not Ready'}
              </Badge>
            </div>
          </div>

          {/* Stream Info */}
          {results.source_resolution && (
            <div className="text-xs text-muted-foreground space-y-1">
              <div>
                <span className="font-medium">Source:</span>{' '}
                {results.source_resolution} @ {results.source_fps}fps ({results.source_codec})
              </div>
              {results.target_resolution && (
                <div>
                  <span className="font-medium">Target:</span>{' '}
                  {results.target_resolution} @ {results.target_fps}fps, {results.target_bitrate}kbps
                </div>
              )}
              {results.estimated_latency_ms && (
                <div>
                  <span className="font-medium">Est. Latency:</span>{' '}
                  {results.estimated_latency_ms}ms
                </div>
              )}
            </div>
          )}

          {/* Error Display */}
          {results.error && (
            <Alert variant="destructive" className="py-2">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription className="text-xs">{results.error}</AlertDescription>
            </Alert>
          )}

          {/* ffmpeg Command */}
          {results.ffmpeg_command && (
            <details className="text-xs">
              <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                View ffmpeg command (debug)
              </summary>
              <code className="block mt-1 p-2 bg-muted rounded text-xs overflow-x-auto whitespace-pre-wrap break-all">
                {results.ffmpeg_command}
              </code>
            </details>
          )}

          <div className="text-xs text-muted-foreground text-right">
            Completed in {results.test_duration_ms}ms
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * PairingsList subcomponent (Story P5-1.8 AC3, AC4)
 *
 * Displays list of paired devices with ability to remove individual pairings.
 */
function PairingsList({ enabled }: { enabled: boolean }) {
  const [removingPairingId, setRemovingPairingId] = useState<string | null>(null);
  const { data: pairingsData, isLoading } = useHomekitPairings({ enabled });
  const removePairingMutation = useHomekitRemovePairing();

  const handleRemovePairing = async (pairingId: string) => {
    try {
      await removePairingMutation.mutateAsync(pairingId);
      setRemovingPairingId(null);
    } catch (err) {
      console.error('Failed to remove pairing:', err);
      setRemovingPairingId(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-4">
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!pairingsData || pairingsData.count === 0) {
    return (
      <div className="text-center py-4 text-muted-foreground text-sm">
        No devices paired yet
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Users className="h-4 w-4" />
          <span>{pairingsData.count} paired {pairingsData.count === 1 ? 'device' : 'devices'}</span>
        </div>
      </div>
      {pairingsData.pairings.map((pairing: HomekitPairing) => (
        <div
          key={pairing.pairing_id}
          className="flex items-center justify-between p-3 border rounded-lg bg-muted/30"
        >
          <div className="flex items-center gap-3">
            {pairing.is_admin ? (
              <Shield className="h-4 w-4 text-blue-500" />
            ) : (
              <User className="h-4 w-4 text-muted-foreground" />
            )}
            <div>
              <div className="font-mono text-sm">
                {pairing.pairing_id.slice(0, 8)}...{pairing.pairing_id.slice(-4)}
              </div>
              <div className="text-xs text-muted-foreground">
                {pairing.is_admin ? 'Admin' : 'User'}
              </div>
            </div>
          </div>

          <AlertDialog
            open={removingPairingId === pairing.pairing_id}
            onOpenChange={(open) => setRemovingPairingId(open ? pairing.pairing_id : null)}
          >
            <AlertDialogTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive hover:text-destructive hover:bg-destructive/10"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Remove Pairing?</AlertDialogTitle>
                <AlertDialogDescription>
                  This device will no longer be able to control your HomeKit accessories.
                  The device will need to re-pair to regain access.
                  {pairing.is_admin && (
                    <span className="block mt-2 text-amber-600 dark:text-amber-400">
                      Warning: This is an admin device. Removing it may affect other users
                      if this is the primary paired device.
                    </span>
                  )}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => handleRemovePairing(pairing.pairing_id)}
                  disabled={removePairingMutation.isPending}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  {removePairingMutation.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Removing...
                    </>
                  ) : (
                    'Remove Pairing'
                  )}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      ))}
    </div>
  );
}

export function HomekitSettings() {
  const [showResetDialog, setShowResetDialog] = useState(false);

  // Fetch status with 10s polling when on settings page
  const { data: status, isLoading, error } = useHomekitStatus({
    refetchInterval: 10000,
  });

  const toggleMutation = useHomekitToggle();
  const resetMutation = useHomekitReset();

  const handleToggle = async (checked: boolean) => {
    try {
      await toggleMutation.mutateAsync(checked);
    } catch (err) {
      console.error('Failed to toggle HomeKit:', err);
    }
  };

  const handleReset = async () => {
    try {
      await resetMutation.mutateAsync();
      setShowResetDialog(false);
    } catch (err) {
      console.error('Failed to reset HomeKit pairing:', err);
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>Error</AlertTitle>
        <AlertDescription>
          Failed to load HomeKit status. {error.message}
        </AlertDescription>
      </Alert>
    );
  }

  if (!status) {
    return null;
  }

  // HAP-python not installed
  if (!status.available) {
    return (
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Smartphone className="h-5 w-5" />
            <CardTitle>HomeKit Integration</CardTitle>
          </div>
          <CardDescription>
            Expose cameras as HomeKit motion sensors for Apple Home
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Alert>
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Not Available</AlertTitle>
            <AlertDescription>
              HomeKit integration requires HAP-python. Install with:{' '}
              <code className="bg-muted px-1 rounded">pip install HAP-python</code>
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Smartphone className="h-5 w-5" />
            <CardTitle>HomeKit Integration</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            {status.running ? (
              <Badge variant="default" className="bg-green-600">
                <Check className="h-3 w-3 mr-1" />
                Running
              </Badge>
            ) : (
              <Badge variant="secondary">
                <X className="h-3 w-3 mr-1" />
                Stopped
              </Badge>
            )}
            {status.paired ? (
              <Badge variant="default" className="bg-blue-600">Paired</Badge>
            ) : (
              <Badge variant="outline">Not Paired</Badge>
            )}
          </div>
        </div>
        <CardDescription>
          Expose cameras as HomeKit motion sensors for Apple Home automations
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Enable Toggle */}
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <Label htmlFor="homekit-enabled">Enable HomeKit</Label>
            <p className="text-sm text-muted-foreground">
              Start the HomeKit accessory server
            </p>
          </div>
          <Switch
            id="homekit-enabled"
            checked={status.enabled}
            onCheckedChange={handleToggle}
            disabled={toggleMutation.isPending}
          />
        </div>

        {/* Error Display */}
        {status.error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{status.error}</AlertDescription>
          </Alert>
        )}

        {/* Status Info */}
        {status.running && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">Bridge Name:</span>
                <span className="ml-2 font-medium">{status.bridge_name}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Port:</span>
                <span className="ml-2 font-medium">{status.port}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Cameras:</span>
                <span className="ml-2 font-medium">{status.accessory_count}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Status:</span>
                <span className="ml-2 font-medium">
                  {status.paired ? 'Paired with Home app' : 'Awaiting pairing'}
                </span>
              </div>
            </div>

            {/* Pairing Info (only when not paired) */}
            {!status.paired && status.setup_code && (
              <div className="border rounded-lg p-4 bg-muted/50">
                <h4 className="font-medium mb-2">Pair with Home App</h4>
                <p className="text-sm text-muted-foreground mb-4">
                  Open the Home app on your iOS device, tap Add Accessory, and enter the code below
                  or scan the QR code.
                </p>

                <div className="flex flex-col items-center gap-4">
                  {/* Setup Code */}
                  <div className="text-center">
                    <Label className="text-xs text-muted-foreground">Pairing Code</Label>
                    <div className="text-3xl font-mono font-bold tracking-wider mt-1">
                      {status.setup_code}
                    </div>
                  </div>

                  {/* QR Code */}
                  {status.qr_code_data && (
                    <div className="text-center">
                      <Label className="text-xs text-muted-foreground">Or Scan QR Code</Label>
                      <div className="mt-2 bg-white p-2 rounded inline-block">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={status.qr_code_data}
                          alt="HomeKit Pairing QR Code"
                          className="w-32 h-32"
                        />
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Paired Devices List (Story P5-1.8 AC3, AC4, AC5) */}
            {status.paired && (
              <div className="border rounded-lg p-4">
                <h4 className="font-medium mb-3">Paired Devices</h4>
                <PairingsList enabled={status.running} />
              </div>
            )}

            {/* Reset Pairing Button */}
            <AlertDialog open={showResetDialog} onOpenChange={setShowResetDialog}>
              <AlertDialogTrigger asChild>
                <Button variant="outline" className="w-full" disabled={resetMutation.isPending}>
                  <RotateCcw className="h-4 w-4 mr-2" />
                  Reset Pairing
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Reset HomeKit Pairing?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will remove the existing HomeKit pairing. You will need to re-add
                    ArgusAI to the Home app with a new pairing code. Any automations using
                    ArgusAI sensors will need to be reconfigured.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={handleReset}
                    disabled={resetMutation.isPending}
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  >
                    {resetMutation.isPending ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        Resetting...
                      </>
                    ) : (
                      'Reset Pairing'
                    )}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>

            {/* Story P7-1.2 AC6: Connectivity Test */}
            <ConnectivityTest enabled={status.running} />
          </div>
        )}

        {/* Instructions when disabled */}
        {!status.enabled && (
          <Alert>
            <Smartphone className="h-4 w-4" />
            <AlertTitle>HomeKit Disabled</AlertTitle>
            <AlertDescription>
              Enable HomeKit to expose your cameras as motion sensors in Apple Home.
              You can then create automations that trigger when motion is detected.
            </AlertDescription>
          </Alert>
        )}
      </CardContent>

      {/* Story P7-1.1 AC6: Diagnostics Panel */}
      {status.enabled && (
        <CardContent className="pt-0">
          <HomeKitDiagnostics enabled={status.running} />
        </CardContent>
      )}
    </Card>
  );
}
