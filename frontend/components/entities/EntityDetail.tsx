/**
 * EntityDetail component - modal/dialog showing entity info and events (Story P4-3.6, P9-4.2, P15-1)
 * AC6: Click entity opens detail view
 * AC7: Shows occurrence history with thumbnails and timestamps
 * AC14: Shows thumbnail from most recent event
 * P9-4.2: Shows paginated event list
 * P15-1.1: Modal scrolling fix for long event lists
 * P15-1.3: Event click opens event detail modal
 * P15-1.4: Back navigation preserves entity modal state
 */

'use client';

import { useState, useCallback, useRef } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { User, Car, HelpCircle, Trash2 } from 'lucide-react';
import { EventDetailModal } from '@/components/events/EventDetailModal';
import type { IEvent } from '@/types/event';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useEntity } from '@/hooks/useEntities';
import { EntityNameEdit } from './EntityNameEdit';
import { EntityEventList } from './EntityEventList';
import { EntityAlertRules } from './EntityAlertRules';
import { cn } from '@/lib/utils';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? '';

  // P15-1.3: State for nested event detail modal
  const [selectedEvent, setSelectedEvent] = useState<IEvent | null>(null);
  const [isEventDetailOpen, setIsEventDetailOpen] = useState(false);

  // P15-1.4: Preserve scroll position when navigating back
  const scrollPositionRef = useRef<number>(0);

  // Fetch full entity detail with recent events
  const { data: entityDetail, isLoading } = useEntity(entity?.id ?? null, 20);

  // P15-1.3: Handle event click from EntityEventList
  const handleEventClick = useCallback((eventId: string, event?: IEvent) => {
    // Store scroll position before opening event detail
    const scrollContainer = document.querySelector('[data-entity-events-scroll]');
    if (scrollContainer) {
      scrollPositionRef.current = scrollContainer.scrollTop;
    }

    if (event) {
      setSelectedEvent(event);
      setIsEventDetailOpen(true);
    }
  }, []);

  // P15-1.4: Handle closing event detail modal
  const handleEventDetailClose = useCallback(() => {
    setIsEventDetailOpen(false);
    setSelectedEvent(null);

    // Restore scroll position after closing
    requestAnimationFrame(() => {
      const scrollContainer = document.querySelector('[data-entity-events-scroll]');
      if (scrollContainer) {
        scrollContainer.scrollTop = scrollPositionRef.current;
      }
    });
  }, []);

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

            {/* Tabs for Events and Alert Rules (Story P9-4.2, P10-1.5, P12-1.5) */}
            <div className="flex-1 pt-4 flex flex-col min-h-0">
              <Tabs defaultValue="events" className="flex flex-col flex-1 min-h-0">
                <TabsList className="flex-shrink-0 w-full grid grid-cols-2">
                  <TabsTrigger value="events">
                    Events ({entityDetail.occurrence_count})
                  </TabsTrigger>
                  <TabsTrigger value="alerts">
                    Alert Rules
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="events" className="flex-1 min-h-0 overflow-hidden mt-3">
                  <EntityEventList
                    entityId={entityDetail.id}
                    onEventClick={handleEventClick}
                  />
                </TabsContent>
                <TabsContent value="alerts" className="flex-1 min-h-0 overflow-auto mt-3">
                  <EntityAlertRules entityId={entityDetail.id} />
                </TabsContent>
              </Tabs>
            </div>
          </div>
        )}
      </DialogContent>

      {/* P15-1.3: Nested Event Detail Modal */}
      <EventDetailModal
        event={selectedEvent}
        open={isEventDetailOpen}
        onClose={handleEventDetailClose}
      />
    </Dialog>
  );
}
