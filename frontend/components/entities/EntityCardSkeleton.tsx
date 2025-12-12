/**
 * EntityCardSkeleton component - loading placeholder for EntityCard (Story P4-3.6)
 * AC12: Loading states displayed during API calls
 */

import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

/**
 * Skeleton loader for EntityCard
 */
export function EntityCardSkeleton() {
  return (
    <Card className="overflow-hidden">
      {/* Thumbnail skeleton */}
      <Skeleton className="w-full h-40" />

      {/* Content skeleton */}
      <div className="p-4 space-y-3">
        {/* Name */}
        <Skeleton className="h-5 w-3/4" />

        {/* Occurrence count */}
        <Skeleton className="h-4 w-1/2" />

        {/* Timestamps */}
        <div className="space-y-1">
          <Skeleton className="h-3 w-2/3" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      </div>
    </Card>
  );
}
