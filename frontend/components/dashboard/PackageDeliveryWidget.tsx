'use client';

/**
 * PackageDeliveryWidget - Dashboard widget showing today's package deliveries
 * Story P7-2.4: Create Package Delivery Dashboard Widget
 *
 * Displays:
 * - Total package count for today
 * - Breakdown by carrier with colored badges
 * - Recent 5 package delivery events with relative timestamps
 * - Empty state when no deliveries today
 * - Loading skeleton while fetching
 * - Auto-refresh every 60 seconds
 */

import { useQuery } from '@tanstack/react-query';
import { formatDistanceToNow } from 'date-fns';
import { Package, Truck, AlertCircle } from 'lucide-react';
import Link from 'next/link';
import { apiClient } from '@/lib/api-client';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { CARRIER_CONFIG } from '@/types/event';

/**
 * Carrier badge component with color coding
 */
function CarrierBadge({ carrier }: { carrier: string | null }) {
  const carrierKey = carrier?.toLowerCase() || 'unknown';
  const config = CARRIER_CONFIG[carrierKey] || CARRIER_CONFIG.unknown;

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${config.bgColor} ${config.color}`}
    >
      {config.display}
    </span>
  );
}

/**
 * Loading skeleton for the widget
 */
function WidgetSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <Skeleton className="h-5 w-40" />
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Total count skeleton */}
        <div className="flex items-center gap-3">
          <Skeleton className="h-10 w-10 rounded-full" />
          <div className="space-y-1.5">
            <Skeleton className="h-7 w-16" />
            <Skeleton className="h-4 w-24" />
          </div>
        </div>
        {/* Carrier breakdown skeleton */}
        <div className="flex flex-wrap gap-2">
          <Skeleton className="h-6 w-16" />
          <Skeleton className="h-6 w-14" />
          <Skeleton className="h-6 w-18" />
        </div>
        {/* Recent events skeleton */}
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex items-center gap-2">
              <Skeleton className="h-4 w-14" />
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-4 w-24" />
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Empty state when no package deliveries today
 */
function EmptyState() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-medium flex items-center gap-2">
          <Package className="h-4 w-4" />
          Package Deliveries
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col items-center justify-center py-6 text-center text-muted-foreground">
          <Truck className="h-10 w-10 mb-3 opacity-40" />
          <p className="text-sm">No package deliveries detected today</p>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Error state when API fails
 */
function ErrorState({ error }: { error: Error }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-medium flex items-center gap-2">
          <Package className="h-4 w-4" />
          Package Deliveries
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col items-center justify-center py-6 text-center text-destructive">
          <AlertCircle className="h-10 w-10 mb-3 opacity-60" />
          <p className="text-sm">Failed to load package deliveries</p>
          <p className="text-xs text-muted-foreground mt-1">{error.message}</p>
        </div>
      </CardContent>
    </Card>
  );
}

export function PackageDeliveryWidget() {
  const {
    data,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ['packageDeliveriesToday'],
    queryFn: () => apiClient.events.getPackageDeliveriesToday(),
    refetchInterval: 60000, // Auto-refresh every 60 seconds
    staleTime: 30000, // Consider data stale after 30 seconds
  });

  if (isLoading) {
    return <WidgetSkeleton />;
  }

  if (isError) {
    return <ErrorState error={error as Error} />;
  }

  if (!data || data.total_count === 0) {
    return <EmptyState />;
  }

  // Sort carriers by count (descending) for display
  const sortedCarriers = Object.entries(data.by_carrier)
    .sort(([, a], [, b]) => b - a);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-medium flex items-center gap-2">
          <Package className="h-4 w-4" />
          Package Deliveries
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Total count with icon */}
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
            <Truck className="h-5 w-5 text-primary" />
          </div>
          <div>
            <p className="text-2xl font-bold">{data.total_count}</p>
            <p className="text-xs text-muted-foreground">
              {data.total_count === 1 ? 'package today' : 'packages today'}
            </p>
          </div>
        </div>

        {/* Carrier breakdown */}
        <div className="flex flex-wrap gap-2">
          {sortedCarriers.map(([carrier, count]) => (
            <div
              key={carrier}
              className="flex items-center gap-1"
            >
              <CarrierBadge carrier={carrier} />
              <span className="text-sm text-muted-foreground">
                {count}
              </span>
            </div>
          ))}
        </div>

        {/* Recent events list */}
        {data.recent_events.length > 0 && (
          <div className="space-y-2 pt-2 border-t">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Recent
            </p>
            <div className="space-y-1.5">
              {data.recent_events.map((event) => (
                <Link
                  key={event.id}
                  href={`/events/${event.id}`}
                  className="flex items-center gap-2 text-sm hover:bg-accent/50 rounded px-1 py-0.5 -mx-1 transition-colors"
                >
                  <CarrierBadge carrier={event.delivery_carrier} />
                  <span className="text-muted-foreground">
                    {formatDistanceToNow(new Date(event.timestamp), { addSuffix: true })}
                  </span>
                  <span className="text-muted-foreground truncate">
                    {event.camera_name}
                  </span>
                </Link>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default PackageDeliveryWidget;
