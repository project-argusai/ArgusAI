/**
 * Session Management Component (Story P15-2.7)
 *
 * Displays active sessions and allows revoking them.
 * Features:
 * - List all active sessions with device info
 * - Mark current session
 * - Revoke individual sessions
 * - Revoke all other sessions
 */

'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Monitor,
  Smartphone,
  Laptop,
  Tablet,
  Globe,
  Clock,
  MapPin,
  Trash2,
  LogOut,
  Loader2,
  Check,
} from 'lucide-react';

import { apiClient } from '@/lib/api-client';
import { parseApiDate, formatLocale } from '@/lib/datetime';
import type { ISession } from '@/types/auth';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

// Determine icon based on device info
function getDeviceIcon(deviceInfo: string | null) {
  if (!deviceInfo) return Monitor;

  const info = deviceInfo.toLowerCase();
  if (info.includes('iphone') || info.includes('android')) return Smartphone;
  if (info.includes('ipad') || info.includes('tablet')) return Tablet;
  if (info.includes('macos') || info.includes('windows') || info.includes('linux')) return Laptop;
  return Monitor;
}

function formatRelativeTime(dateString: string): string {
  const date = parseApiDate(dateString)!;
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins} minute${diffMins === 1 ? '' : 's'} ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
  if (diffDays < 7) return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
  return date.toLocaleDateString();
}

export function SessionManagement() {
  const queryClient = useQueryClient();

  // Fetch sessions
  const { data: sessions, isLoading } = useQuery({
    queryKey: ['sessions'],
    queryFn: () => apiClient.auth.listSessions(),
  });

  // Revoke single session
  const revokeSessionMutation = useMutation({
    mutationFn: (sessionId: string) => apiClient.auth.revokeSession(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
      toast.success('Session revoked successfully');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to revoke session');
    },
  });

  // Revoke all other sessions
  const revokeAllMutation = useMutation({
    mutationFn: () => apiClient.auth.revokeAllSessions(),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
      toast.success(`${response.revoked_count} session${response.revoked_count === 1 ? '' : 's'} revoked`);
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to revoke sessions');
    },
  });

  const otherSessionsCount = sessions?.filter(s => !s.is_current).length || 0;

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Globe className="h-5 w-5" />
            Active Sessions
          </CardTitle>
          <CardDescription>
            Manage your active login sessions across devices
          </CardDescription>
        </div>
        {otherSessionsCount > 0 && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="outline" size="sm">
                <LogOut className="h-4 w-4 mr-2" />
                Sign Out All Others
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Sign Out All Other Sessions</AlertDialogTitle>
                <AlertDialogDescription>
                  This will sign out all {otherSessionsCount} other active session{otherSessionsCount === 1 ? '' : 's'}.
                  Your current session will remain active.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => revokeAllMutation.mutate()}
                  disabled={revokeAllMutation.isPending}
                >
                  {revokeAllMutation.isPending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <LogOut className="h-4 w-4 mr-2" />
                  )}
                  Sign Out All
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {sessions?.map((session) => {
            const DeviceIcon = getDeviceIcon(session.device_info);
            return (
              <div
                key={session.id}
                className={`flex items-center justify-between p-4 rounded-lg border ${
                  session.is_current
                    ? 'border-green-500/30 bg-green-500/5'
                    : 'border-border bg-muted/30'
                }`}
              >
                <div className="flex items-center gap-4">
                  <div className={`p-2 rounded-lg ${
                    session.is_current ? 'bg-green-500/10' : 'bg-muted'
                  }`}>
                    <DeviceIcon className={`h-5 w-5 ${
                      session.is_current ? 'text-green-500' : 'text-muted-foreground'
                    }`} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">
                        {session.device_info || 'Unknown Device'}
                      </span>
                      {session.is_current && (
                        <Badge className="bg-green-500/10 text-green-500 hover:bg-green-500/20">
                          <Check className="h-3 w-3 mr-1" />
                          Current
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-4 mt-1 text-sm text-muted-foreground">
                      {session.ip_address && (
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger className="flex items-center gap-1">
                              <MapPin className="h-3 w-3" />
                              {session.ip_address}
                            </TooltipTrigger>
                            <TooltipContent>IP Address</TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      )}
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger className="flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            {formatRelativeTime(session.last_active_at)}
                          </TooltipTrigger>
                          <TooltipContent>
                            Last active: {formatLocale(session.last_active_at)}
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </div>
                  </div>
                </div>
                {!session.is_current && (
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-muted-foreground hover:text-destructive"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Revoke Session</AlertDialogTitle>
                        <AlertDialogDescription>
                          This will sign out the session on {session.device_info || 'this device'}.
                          The user will need to log in again.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction
                          className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                          onClick={() => revokeSessionMutation.mutate(session.id)}
                        >
                          Revoke
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                )}
              </div>
            );
          })}
          {(!sessions || sessions.length === 0) && (
            <div className="text-center text-muted-foreground py-8">
              No active sessions found
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
