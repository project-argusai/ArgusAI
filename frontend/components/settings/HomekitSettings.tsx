'use client';

/**
 * HomekitSettings component (Story P4-6.1)
 *
 * Settings UI for HomeKit integration with enable toggle, pairing status,
 * QR code display, and reset functionality.
 */
import React, { useState } from 'react';
import { useHomekitStatus, useHomekitToggle, useHomekitReset } from '@/hooks/useHomekitStatus';
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
import { Loader2, AlertCircle, Check, X, RotateCcw, Smartphone } from 'lucide-react';

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
    </Card>
  );
}
