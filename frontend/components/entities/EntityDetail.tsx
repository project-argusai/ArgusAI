/**
 * EntityDetail component - modal/dialog showing entity info and recent events (Story P4-3.6)
 * AC6: Click entity opens detail view
 * AC7: Shows occurrence history with thumbnails and timestamps
 * AC14: Shows thumbnail from most recent event
 */

'use client';

import { formatDistanceToNow } from 'date-fns';
import Link from 'next/link';
import { User, Car, HelpCircle, ExternalLink, Trash2 } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useEntity } from '@/hooks/useEntities';
import { EntityNameEdit } from './EntityNameEdit';
import { cn } from '@/lib/utils';
import type { IEntity } from '@/types/entity';

interface EntityDetailProps {
  /** The entity to display (basic info from list) */
  entity: IEntity | null;
  /** Whether the dialog is open */
  open: boolean;
  /** Callback when dialog is closed */
  onClose: () => void;
  /** Callback when delete is requested */
  onDelete: (entity: IEntity) => void;
}

// Parse timestamp as UTC
function parseUTCTimestamp(timestamp: string): Date {
  const ts = timestamp.includes('Z') || timestamp.includes('+') || timestamp.includes('-', 10)
    ? timestamp
    : timestamp.replace(' ', 'T') + 'Z';
  return new Date(ts);
}

/**
 * Get icon for entity type
 */
function getEntityTypeIcon(entityType: string) {
  switch (entityType) {
    case 'person':
      return <User className="h-4 w-4" />;
    case 'vehicle':
      return <Car className="h-4 w-4" />;
    default:
      return <HelpCircle className="h-4 w-4" />;
  }
}

/**
 * EntityDetail dialog component
 */
export function EntityDetail({
  entity,
  open,
  onClose,
  onDelete,
}: EntityDetailProps) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  // Fetch full entity detail with recent events
  const { data: entityDetail, isLoading } = useEntity(entity?.id ?? null, 20);

  // Get thumbnail from most recent event
  const mostRecentEvent = entityDetail?.recent_events?.[0];
  const thumbnailUrl = mostRecentEvent?.thumbnail_url
    ? mostRecentEvent.thumbnail_url.startsWith('http')
      ? mostRecentEvent.thumbnail_url
      : `${apiUrl}${mostRecentEvent.thumbnail_url}`
    : null;

  const displayName = entityDetail?.name || entity?.name || `Unknown ${entity?.entity_type || 'entity'}`;
  const isNamed = !!(entityDetail?.name || entity?.name);

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] flex flex-col">
        <DialogHeader className="flex-shrink-0">
          <div className="flex items-center justify-between">
            <DialogTitle className="flex items-center gap-2">
              {entity && getEntityTypeIcon(entity.entity_type)}
              <span className={cn(!isNamed && 'text-muted-foreground italic')}>
                {displayName}
              </span>
            </DialogTitle>
          </div>
        </DialogHeader>

        {isLoading && (
          <div className="space-y-4 p-4">
            <Skeleton className="w-full h-48" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <div className="space-y-2 mt-4">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-20 w-full" />
              ))}
            </div>
          </div>
        )}

        {!isLoading && entityDetail && (
          <div className="flex-1 overflow-hidden flex flex-col">
            {/* Main entity info */}
            <div className="flex-shrink-0 space-y-4 pb-4 border-b">
              {/* Thumbnail and basic info row */}
              <div className="flex gap-4">
                {/* Thumbnail */}
                <div className="w-32 h-32 flex-shrink-0 bg-gray-100 rounded-lg overflow-hidden">
                  {thumbnailUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={thumbnailUrl}
                      alt={displayName}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center bg-gray-200">
                      {entityDetail.entity_type === 'person' ? (
                        <User className="w-12 h-12 text-gray-400" />
                      ) : entityDetail.entity_type === 'vehicle' ? (
                        <Car className="w-12 h-12 text-gray-400" />
                      ) : (
                        <HelpCircle className="w-12 h-12 text-gray-400" />
                      )}
                    </div>
                  )}
                </div>

                {/* Info */}
                <div className="flex-1 space-y-2">
                  {/* Name editing */}
                  <EntityNameEdit
                    entityId={entityDetail.id}
                    currentName={entityDetail.name}
                  />

                  {/* Type badge */}
                  <div>
                    <Badge variant="secondary" className="gap-1 capitalize">
                      {getEntityTypeIcon(entityDetail.entity_type)}
                      {entityDetail.entity_type}
                    </Badge>
                  </div>

                  {/* Stats */}
                  <div className="text-sm text-muted-foreground space-y-1">
                    <p>
                      <span className="font-medium">{entityDetail.occurrence_count}</span>{' '}
                      occurrence{entityDetail.occurrence_count !== 1 ? 's' : ''}
                    </p>
                    <p>
                      First seen:{' '}
                      {parseUTCTimestamp(entityDetail.first_seen_at).toLocaleDateString()}
                    </p>
                    <p>
                      Last seen:{' '}
                      {formatDistanceToNow(parseUTCTimestamp(entityDetail.last_seen_at), {
                        addSuffix: true,
                      })}
                    </p>
                  </div>
                </div>
              </div>

              {/* Delete button */}
              <div className="flex justify-end">
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => entity && onDelete(entity)}
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete Entity
                </Button>
              </div>
            </div>

            {/* Recent Events */}
            <div className="flex-1 overflow-hidden pt-4">
              <h4 className="font-medium text-sm mb-3">
                Recent Events ({entityDetail.recent_events.length})
              </h4>

              {entityDetail.recent_events.length === 0 ? (
                <p className="text-sm text-muted-foreground">No events linked to this entity.</p>
              ) : (
                <ScrollArea className="h-[300px]">
                  <div className="space-y-3 pr-4">
                    {entityDetail.recent_events.map((event) => {
                      const eventThumbnail = event.thumbnail_url
                        ? event.thumbnail_url.startsWith('http')
                          ? event.thumbnail_url
                          : `${apiUrl}${event.thumbnail_url}`
                        : null;
                      const eventDate = parseUTCTimestamp(event.timestamp);

                      return (
                        <Link
                          key={event.id}
                          href={`/events?id=${event.id}`}
                          className="flex gap-3 p-2 rounded-lg hover:bg-muted transition-colors group"
                        >
                          {/* Event thumbnail */}
                          <div className="w-20 h-14 flex-shrink-0 bg-gray-100 rounded overflow-hidden">
                            {eventThumbnail ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img
                                src={eventThumbnail}
                                alt="Event thumbnail"
                                className="w-full h-full object-cover"
                              />
                            ) : (
                              <div className="w-full h-full flex items-center justify-center bg-gray-200">
                                <HelpCircle className="w-6 h-6 text-gray-400" />
                              </div>
                            )}
                          </div>

                          {/* Event info */}
                          <div className="flex-1 min-w-0">
                            <p className="text-sm line-clamp-2">{event.description}</p>
                            <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                              <time dateTime={event.timestamp}>
                                {formatDistanceToNow(eventDate, { addSuffix: true })}
                              </time>
                              <span>•</span>
                              <span>
                                {Math.round(event.similarity_score * 100)}% match
                              </span>
                            </div>
                          </div>

                          {/* Link indicator */}
                          <ExternalLink className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
                        </Link>
                      );
                    })}
                  </div>
                </ScrollArea>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
