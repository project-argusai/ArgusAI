/**
 * Events page - displays timeline of AI-classified events with filtering
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import { ChevronUp, AlertCircle, Loader2, Filter } from 'lucide-react';
import { EventCard } from '@/components/events/EventCard';
import { EventFilters } from '@/components/events/EventFilters';
import { EventDetailModal } from '@/components/events/EventDetailModal';
import { useEvents } from '@/lib/hooks/useEvents';
import { apiClient } from '@/lib/api-client';
import type { IEventFilters, IEvent } from '@/types/event';
import type { ICamera } from '@/types/camera';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';

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
        const cameraList = await apiClient.cameras.list({ is_enabled: true });
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

  // Flatten all pages into single array
  const allEvents = data?.pages.flatMap((page) => page.events) ?? [];
  const totalEvents = data?.pages[0]?.total_count ?? 0;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Page Header */}
        <div className="mb-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Events Timeline</h1>
              <p className="mt-2 text-sm text-gray-600">
                {totalEvents > 0
                  ? `Showing ${allEvents.length} of ${totalEvents} events`
                  : 'No events found'}
              </p>
            </div>
            {/* Mobile Filter Toggle */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowFilters(!showFilters)}
              className="lg:hidden"
            >
              <Filter className="w-4 h-4 mr-2" />
              Filters
            </Button>
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
            <Loader2 className="w-12 h-12 text-blue-600 animate-spin" />
            <p className="mt-4 text-sm text-gray-600">Loading events...</p>
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
          <div className="flex flex-col items-center justify-center py-16 bg-white rounded-lg border-2 border-dashed border-gray-300">
            <div className="text-6xl mb-4">📹</div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">No events yet</h3>
            <p className="text-sm text-gray-600 text-center max-w-md">
              Once your cameras start detecting objects, events will appear here. Make sure your
              cameras are enabled and properly configured.
            </p>
          </div>
        )}

        {/* Events Timeline */}
        {!isLoading && !isError && allEvents.length > 0 && (
          <div className="space-y-4">
            {allEvents.map((event) => (
              <EventCard
                key={event.id}
                event={event}
                onClick={() => setSelectedEvent(event)}
              />
            ))}

            {/* Loading More Indicator */}
            {isFetchingNextPage && (
              <div className="flex justify-center py-8">
                <Loader2 className="w-8 h-8 text-blue-600 animate-spin" />
                <span className="ml-2 text-sm text-gray-600">Loading more events...</span>
              </div>
            )}

            {/* End of Results */}
            {!hasNextPage && allEvents.length > 0 && (
              <div className="text-center py-8 text-sm text-gray-500">
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
    </div>
  );
}
