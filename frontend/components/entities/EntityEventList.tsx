/**
 * EntityEventList component - displays events for an entity with virtual scrolling (Story P9-4.2, P9-4.3, P15-1)
 * AC-4.2.1: Shows all linked events
 * AC-4.2.2: Paginated (20 per page) or virtual scrolling for large lists
 * AC-4.2.3: Shows thumbnail, description snippet, date
 * AC-4.2.4: Sorted newest first
 * AC-4.2.5: Empty state for 0 events
 * AC-4.3.1: Remove button visible on each event row
 * AC-4.3.2: Confirmation dialog on remove
 * AC-4.3.3: Event removed from list after confirm
 * AC-4.3.6: Toast notification on success
 * P15-1.1: Modal scrolling with max-height constraint
 * P15-1.2: Virtual scrolling for large event lists (1000+)
 * P15-1.3: Event click opens event detail modal (passes event data)
 * P15-1.5: Event count and scroll position indicator
 */

'use client';

import { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { formatDistanceToNow } from 'date-fns';
import { ExternalLink, HelpCircle, ChevronLeft, ChevronRight, X, Eye } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
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
} from '@/components/ui/alert-dialog';
import { useEntityEvents, useUnlinkEvent } from '@/hooks/useEntities';
import type { IEvent } from '@/types/event';

// P15-1.2: Threshold for enabling virtual scrolling
const VIRTUAL_SCROLL_THRESHOLD = 50;
const ROW_HEIGHT = 80; // Estimated row height in pixels

interface EntityEventListProps {
  /** Entity ID to fetch events for */
  entityId: string;
  /** Optional callback when event is clicked - P15-1.3: now passes full event data */
  onEventClick?: (eventId: string, event?: IEvent) => void;
}

// Parse timestamp as UTC
function parseUTCTimestamp(timestamp: string): Date {
  const ts = timestamp.includes('Z') || timestamp.includes('+') || timestamp.includes('-', 10)
    ? timestamp
    : timestamp.replace(' ', 'T') + 'Z';
  return new Date(ts);
}

/**
 * Convert entity event to IEvent format for EventDetailModal
 */
function convertToIEvent(entityEvent: {
  id: string;
  description: string;
  timestamp: string;
  similarity_score: number;
  thumbnail_url: string | null;
}): IEvent {
  return {
    id: entityEvent.id,
    camera_id: '',
    description: entityEvent.description,
    timestamp: entityEvent.timestamp,
    objects_detected: [],
    confidence: 0,
    thumbnail_path: entityEvent.thumbnail_url,
    thumbnail_base64: null,
    alert_triggered: false,
    created_at: entityEvent.timestamp,
    source_type: 'protect' as const, // Default to protect for entity events
    smart_detection_type: null,
    is_doorbell_ring: false,
  };
}

/**
 * EntityEventList component with virtual scrolling for large lists
 */
export function EntityEventList({ entityId, onEventClick }: EntityEventListProps) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? '';
  const [page, setPage] = useState(1);
  const limit = 100; // Fetch more at once for virtual scrolling

  // P15-1.2: Ref for virtual scroll container
  const parentRef = useRef<HTMLDivElement>(null);

  // P15-1.5: Track visible range for scroll indicator
  const [visibleRange, setVisibleRange] = useState({ start: 0, end: 0 });

  // State for remove confirmation dialog (Story P9-4.3)
  const [eventToRemove, setEventToRemove] = useState<{
    id: string;
    description: string;
  } | null>(null);

  const { data, isLoading, isError } = useEntityEvents(entityId, page, limit);
  const unlinkEventMutation = useUnlinkEvent();

  // Flatten all events from all pages
  const allEvents = useMemo(() => {
    if (!data) return [];
    return data.events || [];
  }, [data]);

  const total = data?.total || 0;
  const useVirtualScrolling = total > VIRTUAL_SCROLL_THRESHOLD;

  // P15-1.2: Virtual scrolling setup
  const virtualizer = useVirtualizer({
    count: allEvents.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 5, // Render 5 extra items outside viewport
    enabled: useVirtualScrolling,
  });

  // P15-1.5: Update visible range when scrolling
  const updateVisibleRange = useCallback(() => {
    if (!parentRef.current || !useVirtualScrolling) return;

    const scrollTop = parentRef.current.scrollTop;
    const containerHeight = parentRef.current.clientHeight;

    const start = Math.floor(scrollTop / ROW_HEIGHT) + 1;
    const end = Math.min(Math.ceil((scrollTop + containerHeight) / ROW_HEIGHT), allEvents.length);

    setVisibleRange({ start, end });
  }, [allEvents.length, useVirtualScrolling]);

  // Set up scroll listener for visible range tracking
  useEffect(() => {
    const scrollElement = parentRef.current;
    if (!scrollElement || !useVirtualScrolling) return;

    scrollElement.addEventListener('scroll', updateVisibleRange);
    updateVisibleRange(); // Initial calculation

    return () => scrollElement.removeEventListener('scroll', updateVisibleRange);
  }, [updateVisibleRange, useVirtualScrolling]);

  // Handle remove confirmation (AC-4.3.3, AC-4.3.6)
  const handleConfirmRemove = async () => {
    if (!eventToRemove) return;

    try {
      await unlinkEventMutation.mutateAsync({
        entityId,
        eventId: eventToRemove.id,
      });
      toast.success('Event removed from entity');
      setEventToRemove(null);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Failed to remove event'
      );
    }
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="flex gap-3 p-2">
            <Skeleton className="w-20 h-14 flex-shrink-0" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-3 w-1/2" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  // Error state
  if (isError) {
    return (
      <p className="text-sm text-destructive">
        Failed to load events. Please try again.
      </p>
    );
  }

  // Empty state (AC-4.2.5)
  if (!data || total === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-muted-foreground">
          No events linked to this entity.
        </p>
      </div>
    );
  }

  const startIdx = (page - 1) * limit + 1;
  const endIdx = Math.min(page * limit, total);
  const totalPages = Math.ceil(total / limit);

  // Render a single event row
  const renderEventRow = (event: typeof allEvents[0], index: number, style?: React.CSSProperties) => {
    const eventThumbnail = event.thumbnail_url
      ? event.thumbnail_url.startsWith('http')
        ? event.thumbnail_url
        : `${apiUrl}${event.thumbnail_url}`
      : null;
    const eventDate = parseUTCTimestamp(event.timestamp);

    return (
      <div
        key={event.id}
        style={style}
        className="flex gap-3 p-2 rounded-lg hover:bg-muted transition-colors group"
      >
        {/* P15-1.3: Click handler passes full event data */}
        <button
          type="button"
          onClick={() => {
            if (onEventClick) {
              onEventClick(event.id, convertToIEvent(event));
            }
          }}
          className="flex gap-3 flex-1 min-w-0 text-left"
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
              {event.similarity_score > 0 && (
                <>
                  <span>•</span>
                  <span>
                    {Math.round(event.similarity_score * 100)}% match
                  </span>
                </>
              )}
            </div>
          </div>

          {/* View indicator */}
          <Eye className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 self-center" />
        </button>

        {/* Remove button (AC-4.3.1) */}
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 self-center text-muted-foreground hover:text-destructive"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setEventToRemove({
              id: event.id,
              description: event.description || 'this event',
            });
          }}
          title="Remove event from entity"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full">
      {/* P15-1.5: Event count badge */}
      <div className="flex items-center justify-between pb-2 flex-shrink-0">
        <Badge variant="secondary" className="gap-1">
          <Eye className="h-3 w-3" />
          {total} event{total !== 1 ? 's' : ''}
        </Badge>

        {/* P15-1.5: Scroll position indicator (only for virtual scrolling) */}
        {useVirtualScrolling && visibleRange.start > 0 && (
          <span className="text-xs text-muted-foreground">
            Showing {visibleRange.start}-{visibleRange.end} of {total}
          </span>
        )}
      </div>

      {/* P15-1.1 & P15-1.2: Scrollable events list with virtual scrolling for large lists */}
      <div
        ref={parentRef}
        data-entity-events-scroll
        className="flex-1 min-h-0 overflow-y-auto max-h-[60vh]"
      >
        {useVirtualScrolling ? (
          // Virtual scrolling for large lists (P15-1.2)
          <div
            style={{
              height: `${virtualizer.getTotalSize()}px`,
              width: '100%',
              position: 'relative',
            }}
          >
            {virtualizer.getVirtualItems().map((virtualRow) => {
              const event = allEvents[virtualRow.index];
              return renderEventRow(event, virtualRow.index, {
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start}px)`,
                height: `${virtualRow.size}px`,
              });
            })}
          </div>
        ) : (
          // Regular rendering for small lists
          <div className="space-y-3 pr-4">
            {allEvents.map((event, index) => renderEventRow(event, index))}
          </div>
        )}
      </div>

      {/* Pagination controls - only show for non-virtual scrolling (AC-4.2.2) */}
      {!useVirtualScrolling && totalPages > 1 && (
        <div className="flex items-center justify-between pt-4 mt-4 border-t flex-shrink-0">
          <p className="text-sm text-muted-foreground">
            Showing {startIdx}-{endIdx} of {total}
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
            >
              <ChevronLeft className="h-4 w-4" />
              Previous
            </Button>
            <span className="text-sm text-muted-foreground px-2">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(p => p + 1)}
              disabled={!data?.has_more}
            >
              Next
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Remove confirmation dialog (AC-4.3.2) */}
      <AlertDialog
        open={!!eventToRemove}
        onOpenChange={(open) => !open && setEventToRemove(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove event from entity?</AlertDialogTitle>
            <AlertDialogDescription>
              This will remove the association between this event and the entity.
              The event itself will not be deleted.
              {eventToRemove?.description && (
                <span className="block mt-2 text-foreground font-medium line-clamp-2">
                  &ldquo;{eventToRemove.description}&rdquo;
                </span>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={unlinkEventMutation.isPending}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmRemove}
              disabled={unlinkEventMutation.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {unlinkEventMutation.isPending ? 'Removing...' : 'Remove'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
