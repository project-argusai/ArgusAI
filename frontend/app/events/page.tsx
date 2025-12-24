/**
 * Events page - displays timeline of AI-classified events with filtering
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import { ChevronUp, AlertCircle, Loader2, Filter, RefreshCw, Trash2, X, CheckSquare } from 'lucide-react';
import { EventCard } from '@/components/events/EventCard';
import { DoorbellEventCard } from '@/components/events/DoorbellEventCard';
import { EventFilters } from '@/components/events/EventFilters';
import { EventDetailModal } from '@/components/events/EventDetailModal';
import { useEvents, useInvalidateEvents } from '@/lib/hooks/useEvents';
import { useWebSocket } from '@/lib/hooks/useWebSocket';
import { apiClient } from '@/lib/api-client';
import type { IEventFilters, IEvent } from '@/types/event';
import type { ICamera } from '@/types/camera';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Checkbox } from '@/components/ui/checkbox';
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
import { toast } from 'sonner';

// Helper: Parse URL params to filters
function parseFiltersFromURL(searchParams: URLSearchParams): IEventFilters {
  const filters: IEventFilters = {};

  const search = searchParams.get('search');
  if (search) filters.search = search;

  const cameraId = searchParams.get('camera_id');
  if (cameraId) filters.camera_id = cameraId;

  const startDate = searchParams.get('start_date');
  if (startDate) filters.start_date = startDate;

  const endDate = searchParams.get('end_date');
  if (endDate) filters.end_date = endDate;

  const objects = searchParams.get('objects');
  if (objects) filters.objects = objects.split(',');

  const minConfidence = searchParams.get('min_confidence');
  if (minConfidence) filters.min_confidence = parseInt(minConfidence, 10);

  const sourceType = searchParams.get('source');
  if (sourceType && ['rtsp', 'usb', 'protect'].includes(sourceType)) {
    filters.source_type = sourceType as 'rtsp' | 'usb' | 'protect';
  }

  const smartDetectionType = searchParams.get('smart_detection_type');
  if (smartDetectionType && ['person', 'vehicle', 'package', 'animal', 'motion', 'ring'].includes(smartDetectionType)) {
    filters.smart_detection_type = smartDetectionType as 'person' | 'vehicle' | 'package' | 'animal' | 'motion' | 'ring';
  }

  // Story P3-7.6: Analysis mode filters
  const analysisMode = searchParams.get('analysis_mode');
  if (analysisMode && ['single_frame', 'multi_frame', 'video_native'].includes(analysisMode)) {
    filters.analysis_mode = analysisMode as 'single_frame' | 'multi_frame' | 'video_native';
  }

  const hasFallback = searchParams.get('has_fallback');
  if (hasFallback === 'true') {
    filters.has_fallback = true;
  }

  const lowConfidence = searchParams.get('low_confidence');
  if (lowConfidence === 'true') {
    filters.low_confidence = true;
  }

  return filters;
}

// Helper: Convert filters to URL params
function filtersToURLParams(filters: IEventFilters): URLSearchParams {
  const params = new URLSearchParams();

  if (filters.search) params.set('search', filters.search);
  if (filters.camera_id) params.set('camera_id', filters.camera_id);
  if (filters.start_date) params.set('start_date', filters.start_date);
  if (filters.end_date) params.set('end_date', filters.end_date);
  if (filters.objects && filters.objects.length > 0) {
    params.set('objects', filters.objects.join(','));
  }
  if (filters.min_confidence !== undefined && filters.min_confidence > 0) {
    params.set('min_confidence', filters.min_confidence.toString());
  }
  if (filters.source_type) {
    params.set('source', filters.source_type);
  }
  if (filters.smart_detection_type) {
    params.set('smart_detection_type', filters.smart_detection_type);
  }
  // Story P3-7.6: Analysis mode filters
  if (filters.analysis_mode) {
    params.set('analysis_mode', filters.analysis_mode);
  }
  if (filters.has_fallback) {
    params.set('has_fallback', 'true');
  }
  if (filters.low_confidence) {
    params.set('low_confidence', 'true');
  }

  return params;
}

export default function EventsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [filters, setFilters] = useState<IEventFilters>(() => {
    // Initialize filters from URL params
    return parseFiltersFromURL(searchParams);
  });
  const [selectedEvent, setSelectedEvent] = useState<IEvent | null>(null);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [cameras, setCameras] = useState<ICamera[]>([]);
  const [newEventsCount, setNewEventsCount] = useState(0);
  const invalidateEvents = useInvalidateEvents();

  // FF-010: Multi-select state
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // FF-002: Subscribe to WebSocket for real-time updates
  const handleNewEvent = useCallback((data: { event_id: string; camera_id: string; description: string | null }) => {
    // Increment new events counter
    setNewEventsCount((prev) => prev + 1);
    // Show toast notification
    toast.info('New event detected', {
      description: data.description?.slice(0, 60) || 'A new event was captured',
      duration: 3000,
    });
  }, []);

  useWebSocket({
    autoConnect: true,
    onNewEvent: handleNewEvent,
  });

  // Handler to refresh and clear new events indicator
  const handleRefresh = useCallback(() => {
    setNewEventsCount(0);
    invalidateEvents();
  }, [invalidateEvents]);

  // FF-010: Selection handlers
  const toggleSelection = useCallback((eventId: string) => {
    setSelectedIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(eventId)) {
        newSet.delete(eventId);
      } else {
        newSet.add(eventId);
      }
      return newSet;
    });
  }, []);

  const toggleSelectAll = useCallback((allEventIds: string[]) => {
    setSelectedIds(prev => {
      if (prev.size === allEventIds.length) {
        // All selected, deselect all
        return new Set();
      }
      // Select all
      return new Set(allEventIds);
    });
  }, []);

  const exitSelectionMode = useCallback(() => {
    setSelectionMode(false);
    setSelectedIds(new Set());
  }, []);

  const handleBulkDelete = useCallback(async () => {
    if (selectedIds.size === 0) return;

    setIsDeleting(true);
    try {
      const result = await apiClient.events.deleteMany(Array.from(selectedIds));
      toast.success(`Deleted ${result.deleted_count} events`);
      setSelectedIds(new Set());
      setSelectionMode(false);
      invalidateEvents();
    } catch (error) {
      toast.error('Failed to delete events', {
        description: error instanceof Error ? error.message : 'Unknown error',
      });
    } finally {
      setIsDeleting(false);
      setShowDeleteConfirm(false);
    }
  }, [selectedIds, invalidateEvents]);

  // Sync filters to URL params
  useEffect(() => {
    const params = filtersToURLParams(filters);
    const queryString = params.toString();
    const newURL = queryString ? `${pathname}?${queryString}` : pathname;
    router.replace(newURL, { scroll: false });
  }, [filters, pathname, router]);

  // Fetch cameras for filter
  useEffect(() => {
    const fetchCameras = async () => {
      try {
        const cameraList = await apiClient.cameras.list();
        setCameras(cameraList);
      } catch (error) {
        console.error('Failed to fetch cameras:', error);
      }
    };
    fetchCameras();
  }, []);

  // Fetch events with infinite query
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
    isError,
    error,
  } = useEvents(filters);

  // Handle scroll-to-top button visibility
  useEffect(() => {
    const handleScroll = () => {
      setShowScrollTop(window.scrollY > 200);
    };

    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // Infinite scroll handler
  const handleScroll = useCallback(() => {
    if (
      window.innerHeight + window.scrollY >=
        document.documentElement.scrollHeight - 500 &&
      hasNextPage &&
      !isFetchingNextPage
    ) {
      fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  useEffect(() => {
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, [handleScroll]);

  // Scroll to top handler
  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Flatten all pages into single array and deduplicate by id
  // (new events can arrive while scrolling, causing duplicates across pages)
  const allEvents = data?.pages.flatMap((page) => page.events).filter(
    (event, index, self) => self.findIndex((e) => e.id === event.id) === index
  ) ?? [];
  const totalEvents = data?.pages[0]?.total_count ?? 0;

  return (
    <div className="min-h-screen">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Page Header - Story P9-6.5: Fixed button positioning, P10-1.4: Clear DesktopToolbar zone */}
        <div className="mb-6 lg:pr-64">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
            <div className="min-w-0 flex-1">
              <h1 className="text-3xl font-bold tracking-tight">Events Timeline</h1>
              <p className="mt-2 text-sm text-muted-foreground">
                {totalEvents > 0
                  ? `Showing ${allEvents.length} of ${totalEvents} events`
                  : 'No events found'}
              </p>
            </div>
            {/* Action buttons - responsive layout with proper touch targets */}
            <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">
              {/* FF-010: Selection mode toggle */}
              {!selectionMode && allEvents.length > 0 && (
                <Button
                  variant="outline"
                  size="default"
                  onClick={() => setSelectionMode(true)}
                  className="h-11 min-w-[44px] sm:h-9"
                >
                  <CheckSquare className="w-4 h-4 mr-2" />
                  Select
                </Button>
              )}
              {/* FF-002: Refresh button with new events indicator */}
              <Button
                variant={newEventsCount > 0 ? 'default' : 'outline'}
                size="default"
                onClick={handleRefresh}
                className="relative h-11 min-w-[44px] sm:h-9"
              >
                <RefreshCw className="w-4 h-4 mr-2" />
                {newEventsCount > 0 ? `${newEventsCount} new` : 'Refresh'}
              </Button>
              {/* Mobile Filter Toggle */}
              <Button
                variant="outline"
                size="default"
                onClick={() => setShowFilters(!showFilters)}
                className="lg:hidden h-11 min-w-[44px] sm:h-9"
              >
                <Filter className="w-4 h-4 mr-2" />
                Filters
              </Button>
            </div>
          </div>
        </div>

        {/* Two-column layout: Filters + Timeline */}
        <div className="flex flex-col lg:flex-row gap-6">
          {/* Filters Sidebar - Desktop: always visible, Mobile: collapsible */}
          <aside
            className={`lg:block lg:w-80 flex-shrink-0 ${
              showFilters ? 'block' : 'hidden'
            }`}
          >
            <EventFilters
              filters={filters}
              onFiltersChange={setFilters}
              cameras={cameras}
            />
          </aside>

          {/* Main Content - Timeline */}
          <main className="flex-1 min-w-0">

        {/* Loading State */}
        {isLoading && (
          <div className="flex flex-col items-center justify-center py-12">
            <Loader2 className="w-12 h-12 text-primary animate-spin" />
            <p className="mt-4 text-sm text-muted-foreground">Loading events...</p>
          </div>
        )}

        {/* Error State */}
        {isError && (
          <Alert variant="destructive" className="mb-6">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              Failed to load events: {error instanceof Error ? error.message : 'Unknown error'}
            </AlertDescription>
          </Alert>
        )}

        {/* Empty State */}
        {!isLoading && !isError && allEvents.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 bg-card rounded-lg border-2 border-dashed border-border">
            <div className="text-6xl mb-4">📹</div>
            <h3 className="text-lg font-semibold mb-2">No events yet</h3>
            <p className="text-sm text-muted-foreground text-center max-w-md">
              Once your cameras start detecting objects, events will appear here. Make sure your
              cameras are enabled and properly configured.
            </p>
          </div>
        )}

        {/* Events Timeline */}
        {!isLoading && !isError && allEvents.length > 0 && (
          <div className="space-y-4">
            {/* FF-010: Selection header when in selection mode */}
            {selectionMode && (
              <div className="flex items-center justify-between p-3 bg-muted rounded-lg sticky top-0 z-10">
                <div className="flex items-center gap-3">
                  <Checkbox
                    checked={selectedIds.size === allEvents.length && allEvents.length > 0}
                    onCheckedChange={() => toggleSelectAll(allEvents.map(e => e.id))}
                    aria-label="Select all events"
                  />
                  <span className="text-sm font-medium">
                    {selectedIds.size > 0
                      ? `${selectedIds.size} selected`
                      : 'Select events'}
                  </span>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={exitSelectionMode}
                >
                  <X className="w-4 h-4 mr-1" />
                  Cancel
                </Button>
              </div>
            )}

            {allEvents.map((event) => (
              <div key={event.id} className="flex items-start gap-3">
                {/* FF-010: Selection checkbox */}
                {selectionMode && (
                  <div className="pt-4 pl-1">
                    <Checkbox
                      checked={selectedIds.has(event.id)}
                      onCheckedChange={() => toggleSelection(event.id)}
                      aria-label={`Select event ${event.id}`}
                    />
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  {event.is_doorbell_ring ? (
                    <DoorbellEventCard
                      event={event}
                      onClick={() => !selectionMode && setSelectedEvent(event)}
                    />
                  ) : (
                    <EventCard
                      event={event}
                      onClick={() => !selectionMode && setSelectedEvent(event)}
                    />
                  )}
                </div>
              </div>
            ))}

            {/* Loading More Indicator */}
            {isFetchingNextPage && (
              <div className="flex justify-center py-8">
                <Loader2 className="w-8 h-8 text-primary animate-spin" />
                <span className="ml-2 text-sm text-muted-foreground">Loading more events...</span>
              </div>
            )}

            {/* End of Results */}
            {!hasNextPage && allEvents.length > 0 && (
              <div className="text-center py-8 text-sm text-muted-foreground">
                You&apos;ve reached the end of the timeline
              </div>
            )}
          </div>
        )}

          </main>
        </div>

        {/* Scroll to Top Button */}
        {showScrollTop && (
          <Button
            onClick={scrollToTop}
            className="fixed bottom-6 right-6 rounded-full w-12 h-12 shadow-lg"
            size="icon"
            aria-label="Scroll to top"
          >
            <ChevronUp className="w-6 h-6" />
          </Button>
        )}
      </div>

      {/* Event Detail Modal */}
      <EventDetailModal
        event={selectedEvent}
        open={!!selectedEvent}
        onClose={() => setSelectedEvent(null)}
        allEvents={allEvents}
        onNavigate={setSelectedEvent}
      />

      {/* FF-010: Floating action bar when items selected */}
      {selectionMode && selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50">
          <div className="flex items-center gap-3 bg-background border border-border rounded-lg shadow-lg px-4 py-3">
            <span className="text-sm font-medium">
              {selectedIds.size} event{selectedIds.size !== 1 ? 's' : ''} selected
            </span>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setShowDeleteConfirm(true)}
              disabled={isDeleting}
            >
              <Trash2 className="w-4 h-4 mr-2" />
              Delete
            </Button>
          </div>
        </div>
      )}

      {/* FF-010: Delete confirmation dialog */}
      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {selectedIds.size} event{selectedIds.size !== 1 ? 's' : ''}?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. This will permanently delete the selected events
              and their associated thumbnails and frames.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleBulkDelete}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Deleting...
                </>
              ) : (
                <>
                  <Trash2 className="w-4 h-4 mr-2" />
                  Delete
                </>
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
