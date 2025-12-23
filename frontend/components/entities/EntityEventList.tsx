/**
 * EntityEventList component - displays paginated events for an entity (Story P9-4.2, P9-4.3)
 * AC-4.2.1: Shows all linked events
 * AC-4.2.2: Paginated (20 per page)
 * AC-4.2.3: Shows thumbnail, description snippet, date
 * AC-4.2.4: Sorted newest first
 * AC-4.2.5: Empty state for 0 events
 * AC-4.3.1: Remove button visible on each event row
 * AC-4.3.2: Confirmation dialog on remove
 * AC-4.3.3: Event removed from list after confirm
 * AC-4.3.6: Toast notification on success
 */

'use client';

import { useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import Link from 'next/link';
import { ExternalLink, HelpCircle, ChevronLeft, ChevronRight, X } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ScrollArea } from '@/components/ui/scroll-area';
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

interface EntityEventListProps {
  /** Entity ID to fetch events for */
  entityId: string;
  /** Optional callback when event is clicked */
  onEventClick?: (eventId: string) => void;
}

// Parse timestamp as UTC
function parseUTCTimestamp(timestamp: string): Date {
  const ts = timestamp.includes('Z') || timestamp.includes('+') || timestamp.includes('-', 10)
    ? timestamp
    : timestamp.replace(' ', 'T') + 'Z';
  return new Date(ts);
}

/**
 * EntityEventList component with pagination and remove functionality
 */
export function EntityEventList({ entityId, onEventClick }: EntityEventListProps) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  const [page, setPage] = useState(1);
  const limit = 20;

  // State for remove confirmation dialog (Story P9-4.3)
  const [eventToRemove, setEventToRemove] = useState<{
    id: string;
    description: string;
  } | null>(null);

  const { data, isLoading, isError } = useEntityEvents(entityId, page, limit);
  const unlinkEventMutation = useUnlinkEvent();

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
  if (!data || data.total === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-muted-foreground">
          No events linked to this entity.
        </p>
      </div>
    );
  }

  const { events, total, has_more } = data;
  const startIdx = (page - 1) * limit + 1;
  const endIdx = Math.min(page * limit, total);
  const totalPages = Math.ceil(total / limit);

  return (
    <div className="flex flex-col h-full">
      {/* Events list (AC-4.2.3) */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="space-y-3 pr-4">
          {events.map((event) => {
            const eventThumbnail = event.thumbnail_url
              ? event.thumbnail_url.startsWith('http')
                ? event.thumbnail_url
                : `${apiUrl}${event.thumbnail_url}`
              : null;
            const eventDate = parseUTCTimestamp(event.timestamp);

            return (
              <div
                key={event.id}
                className="flex gap-3 p-2 rounded-lg hover:bg-muted transition-colors group"
              >
                <Link
                  href={`/events?id=${event.id}`}
                  onClick={(e) => {
                    if (onEventClick) {
                      e.preventDefault();
                      onEventClick(event.id);
                    }
                  }}
                  className="flex gap-3 flex-1 min-w-0"
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

                  {/* Link indicator */}
                  <ExternalLink className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 self-center" />
                </Link>

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
          })}
        </div>
      </ScrollArea>

      {/* Pagination controls (AC-4.2.2) */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-4 mt-4 border-t">
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
              disabled={!has_more}
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
