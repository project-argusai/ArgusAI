'use client';

/**
 * DeviceManager - Manage registered mobile devices (Story P12-2.3)
 *
 * Provides UI for:
 * - Listing user's registered devices with platform icons
 * - Renaming devices
 * - Removing devices
 * - Bulk cleanup of inactive devices (90+ days)
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { formatRelative } from '@/lib/datetime';
import {
  Smartphone,
  Trash2,
  Pencil,
  AlertTriangle,
  Loader2,
  Apple,
  Globe,
} from 'lucide-react';
import { toast } from 'sonner';

import { apiClient } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

interface Device {
  id: string;
  device_id: string;
  platform: 'ios' | 'android' | 'web';
  name: string | null;
  device_model: string | null;
  pairing_confirmed: boolean;
  inactive_warning: boolean;
  last_seen_at: string | null;
  created_at: string;
}

function PlatformIcon({ platform }: { platform: string }) {
  switch (platform) {
    case 'ios':
      return <Apple className="h-4 w-4" />;
    case 'android':
      return <Smartphone className="h-4 w-4" />;
    case 'web':
      return <Globe className="h-4 w-4" />;
    default:
      return <Smartphone className="h-4 w-4" />;
  }
}

export function DeviceManager() {
  const queryClient = useQueryClient();
  const [editingDevice, setEditingDevice] = useState<Device | null>(null);
  const [newName, setNewName] = useState('');

  // Fetch devices
  // BUG-019 Fix: Poll for new devices since Device record is created when
  // mobile app exchanges code for tokens (after web confirmation)
  const { data, isLoading, error } = useQuery({
    queryKey: ['devices'],
    queryFn: () => apiClient.push.listDevices(),
    refetchInterval: 5000, // Poll every 5 seconds to catch new devices
  });

  // Rename device mutation
  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      apiClient.push.updateDevice(id, { name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devices'] });
      toast.success('Device renamed');
      setEditingDevice(null);
      setNewName('');
    },
    onError: () => {
      toast.error('Failed to rename device');
    },
  });

  // Delete device mutation
  const deleteMutation = useMutation({
    mutationFn: (deviceId: string) => apiClient.push.revokeDevice(deviceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devices'] });
      toast.success('Device removed');
    },
    onError: () => {
      toast.error('Failed to remove device');
    },
  });

  // Cleanup inactive devices mutation
  const cleanupMutation = useMutation({
    mutationFn: () => apiClient.push.cleanupInactiveDevices(),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['devices'] });
      toast.success(`Removed ${data.removed_count} inactive device(s)`);
    },
    onError: () => {
      toast.error('Failed to cleanup inactive devices');
    },
  });

  const devices = (data?.devices ?? []) as Device[];
  const inactiveCount = devices.filter((d) => d.inactive_warning).length;

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Smartphone className="h-5 w-5" />
            Registered Devices
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-destructive" />
            Failed to load devices
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Smartphone className="h-5 w-5" />
              Registered Devices
            </CardTitle>
            <CardDescription>
              Manage your mobile devices registered for push notifications
            </CardDescription>
          </div>
          {inactiveCount > 0 && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" size="sm">
                  <Trash2 className="h-4 w-4 mr-2" />
                  Cleanup {inactiveCount} Inactive
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Cleanup Inactive Devices?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will remove {inactiveCount} device(s) that haven&apos;t been seen in over 90 days.
                    This action cannot be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={() => cleanupMutation.mutate()}
                    disabled={cleanupMutation.isPending}
                  >
                    {cleanupMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                    Remove Inactive Devices
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : devices.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Smartphone className="h-12 w-12 mx-auto mb-4 opacity-30" />
            <p>No devices registered yet</p>
            <p className="text-sm mt-1">
              Devices will appear here when you register from a mobile app
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {devices.map((device) => (
              <div
                key={device.id}
                className={`flex items-center justify-between p-4 rounded-lg border ${
                  device.inactive_warning ? 'border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950' : ''
                }`}
              >
                <div className="flex items-center gap-4 min-w-0">
                  <div className="p-2 rounded-full bg-muted">
                    <PlatformIcon platform={device.platform} />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium truncate">
                        {device.name || device.device_model || `${device.platform} device`}
                      </span>
                      {device.inactive_warning && (
                        <Badge variant="destructive" className="text-xs">
                          Inactive
                        </Badge>
                      )}
                      {device.pairing_confirmed && (
                        <Badge variant="secondary" className="text-xs">
                          Paired
                        </Badge>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      <span className="capitalize">{device.platform}</span>
                      {device.device_model && ` • ${device.device_model}`}
                      {device.last_seen_at && (
                        <>
                          {' • Last seen '}
                          {formatRelative(device.last_seen_at)}
                        </>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => {
                      setEditingDevice(device);
                      setNewName(device.name || '');
                    }}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="ghost" size="icon">
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Remove Device?</AlertDialogTitle>
                        <AlertDialogDescription>
                          This will unregister &quot;{device.name || device.device_model || 'this device'}&quot;
                          from push notifications. You can re-register it from the mobile app.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction
                          onClick={() => deleteMutation.mutate(device.device_id)}
                          disabled={deleteMutation.isPending}
                        >
                          Remove
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>

      {/* Rename Dialog */}
      <Dialog open={!!editingDevice} onOpenChange={(open) => !open && setEditingDevice(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename Device</DialogTitle>
            <DialogDescription>
              Give this device a friendly name to easily identify it.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="My iPhone"
              maxLength={100}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingDevice(null)}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                if (editingDevice) {
                  renameMutation.mutate({ id: editingDevice.id, name: newName });
                }
              }}
              disabled={renameMutation.isPending || !newName.trim()}
            >
              {renameMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
