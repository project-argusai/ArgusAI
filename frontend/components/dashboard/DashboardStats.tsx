/**
 * Dashboard Stats component
 * Shows real-time statistics for events and cameras
 * FF-006: Updated for WebSocket-based real-time updates
 */

'use client';

import { useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { cameraKeys } from '@/hooks/useCamerasQuery';
import { useWebSocket } from '@/lib/hooks/useWebSocket';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Calendar, Camera, Bell, TrendingUp } from 'lucide-react';

export function DashboardStats() {
  const queryClient = useQueryClient();

  // FF-006: Subscribe to WebSocket for real-time event updates
  const handleNewEvent = useCallback(() => {
    // Invalidate event queries to refresh counts
    queryClient.invalidateQueries({ queryKey: ['events', 'stats'] });
    queryClient.invalidateQueries({ queryKey: ['events', 'today'] });
  }, [queryClient]);

  useWebSocket({
    autoConnect: true,
    onNewEvent: handleNewEvent,
  });

  // Fetch total events count
  const { data: eventsData } = useQuery({
    queryKey: ['events', 'stats'],
    queryFn: () => apiClient.events.list({}, { skip: 0, limit: 1 }),
    staleTime: 30 * 1000,
  });

  // Fetch today's events count
  const { data: todayData } = useQuery({
    queryKey: ['events', 'today'],
    queryFn: () => {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      return apiClient.events.list(
        { start_date: today.toISOString() },
        { skip: 0, limit: 1 }
      );
    },
    staleTime: 30 * 1000,
  });

  // Fetch cameras using standardized query keys (Story P6-1.4)
  const { data: camerasData } = useQuery({
    queryKey: cameraKeys.list(),
    queryFn: () => apiClient.cameras.list(),
    staleTime: 30 * 1000, // Consistent 30s stale time with useCamerasQuery
    refetchOnWindowFocus: true,
  });

  // Fetch alert rules
  const { data: rulesData } = useQuery({
    queryKey: ['alertRules'],
    queryFn: () => apiClient.alertRules.list(),
    staleTime: 60 * 1000,
  });

  const enabledCameras = camerasData?.filter((c) => c.is_enabled).length ?? 0;

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Total Events</CardTitle>
          <Calendar className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {eventsData?.total_count ?? '--'}
          </div>
          <p className="text-xs text-muted-foreground">
            All time detected events
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Active Cameras</CardTitle>
          <Camera className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {enabledCameras} / {camerasData?.length ?? 0}
          </div>
          <p className="text-xs text-muted-foreground">
            Enabled and monitoring
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Alert Rules</CardTitle>
          <Bell className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {rulesData?.data?.length ?? 0}
          </div>
          <p className="text-xs text-muted-foreground">
            Active notification rules
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Today&apos;s Activity</CardTitle>
          <TrendingUp className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {todayData?.total_count ?? 0}
          </div>
          <p className="text-xs text-muted-foreground">
            Events detected today
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
