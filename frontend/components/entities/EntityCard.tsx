/**
 * EntityCard component - displays individual entity in the entities list (Story P4-3.6)
 * Shows thumbnail, name, type badge, occurrence count, and timestamps
 * Story P7-4.2: Add "Add Alert" button (AC3, AC4)
 * Story P7-4.3: Open EntityAlertModal when "Add Alert" clicked (AC1)
 */

'use client';

import { memo, useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { User, Car, HelpCircle, Bell } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { EntityAlertModal } from './EntityAlertModal';
import type { IEntity } from '@/types/entity';

interface EntityCardProps {
  entity: IEntity;
  /** Thumbnail URL from the most recent event */
  thumbnailUrl?: string | null;
  onClick: () => void;
}

/**
 * Get icon for entity type
 */
function getEntityTypeIcon(entityType: string) {
  switch (entityType) {
    case 'person':
      return <User className="h-3.5 w-3.5" />;
    case 'vehicle':
      return <Car className="h-3.5 w-3.5" />;
    default:
      return <HelpCircle className="h-3.5 w-3.5" />;
  }
}

/**
 * Get badge variant for entity type
 */
function getEntityTypeBadgeVariant(entityType: string): 'default' | 'secondary' | 'outline' {
  switch (entityType) {
    case 'person':
      return 'default';
    case 'vehicle':
      return 'secondary';
    default:
      return 'outline';
  }
}

// Parse timestamp as UTC
function parseUTCTimestamp(timestamp: string): Date {
  const ts = timestamp.includes('Z') || timestamp.includes('+') || timestamp.includes('-', 10)
    ? timestamp
    : timestamp.replace(' ', 'T') + 'Z';
  return new Date(ts);
}

export const EntityCard = memo(function EntityCard({
  entity,
  thumbnailUrl,
  onClick,
}: EntityCardProps) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  // Story P7-4.3: Modal state for EntityAlertModal (AC1)
  const [isAlertModalOpen, setIsAlertModalOpen] = useState(false);

  // Story P7-4.3 AC1: "Add Alert" button opens modal
  const handleAddAlert = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent card click from triggering
    setIsAlertModalOpen(true);
  };

  // Build full thumbnail URL if path is relative
  const fullThumbnailUrl = thumbnailUrl
    ? thumbnailUrl.startsWith('http')
      ? thumbnailUrl
      : `${apiUrl}${thumbnailUrl}`
    : null;

  const firstSeenDate = parseUTCTimestamp(entity.first_seen_at);
  const lastSeenDate = parseUTCTimestamp(entity.last_seen_at);
  const lastSeenRelative = formatDistanceToNow(lastSeenDate, { addSuffix: true });

  // Display name with fallback
  const displayName = entity.name || `Unknown ${entity.entity_type}`;
  const isNamed = !!entity.name;

  return (
    <Card
      className={cn(
        'overflow-hidden cursor-pointer transition-all hover:shadow-md hover:border-blue-300',
        'flex flex-col'
      )}
      onClick={onClick}
    >
      {/* Thumbnail Section */}
      <div className="relative w-full h-40 bg-gray-100">
        {fullThumbnailUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={fullThumbnailUrl}
            alt={`${displayName} thumbnail`}
            className="w-full h-full object-cover"
            onError={(e) => {
              // Hide broken image
              (e.target as HTMLImageElement).style.display = 'none';
            }}
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-200">
            {entity.entity_type === 'person' ? (
              <User className="w-12 h-12 text-gray-400" />
            ) : entity.entity_type === 'vehicle' ? (
              <Car className="w-12 h-12 text-gray-400" />
            ) : (
              <HelpCircle className="w-12 h-12 text-gray-400" />
            )}
          </div>
        )}

        {/* Entity Type Badge - positioned in corner */}
        <div className="absolute top-2 right-2">
          <Badge variant={getEntityTypeBadgeVariant(entity.entity_type)} className="gap-1">
            {getEntityTypeIcon(entity.entity_type)}
            <span className="capitalize">{entity.entity_type}</span>
          </Badge>
        </div>
      </div>

      {/* Entity Details */}
      <div className="p-4 space-y-2">
        {/* Name */}
        <h3 className={cn(
          'font-medium text-base truncate',
          !isNamed && 'text-muted-foreground italic'
        )}>
          {displayName}
        </h3>

        {/* Occurrence count */}
        <p className="text-sm text-muted-foreground">
          Seen {entity.occurrence_count} time{entity.occurrence_count !== 1 ? 's' : ''}
        </p>

        {/* Timestamps */}
        <div className="text-xs text-muted-foreground space-y-1">
          <p>Last seen: {lastSeenRelative}</p>
          <p>First seen: {firstSeenDate.toLocaleDateString()}</p>
        </div>

        {/* Story P7-4.3 AC1: Add Alert button opens modal */}
        <div className="pt-2">
          <Button
            variant="outline"
            size="sm"
            className="w-full gap-2"
            onClick={handleAddAlert}
            aria-label={`Add alert for ${displayName}`}
          >
            <Bell className="h-4 w-4" />
            Add Alert
          </Button>
        </div>
      </div>

      {/* Story P7-4.3: Entity Alert Modal */}
      <EntityAlertModal
        isOpen={isAlertModalOpen}
        onClose={() => setIsAlertModalOpen(false)}
        entity={entity}
      />
    </Card>
  );
});
