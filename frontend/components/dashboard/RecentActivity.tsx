/**
 * Recent Activity component for dashboard
 * Shows the 5 most recent events with links to full timeline
 */

'use client';

import { useRecentEvents, useInvalidateEvents } from '@/lib/hooks/useEvents';
import { useWebSocket } from '@/lib/hooks/useWebSocket';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Activity, ArrowRight, Camera, Clock, AlertCircle } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import Link from 'next/link';
import { getConfidenceColor } from '@/types/event';

// Parse timestamp as UTC (backend stores UTC without timezone indicator)
function parseUTCTimestamp(timestamp: string): Date {
  const ts = timestamp.includes('Z') || timestamp.includes('+') || timestamp.includes('-', 10)
    ? timestamp
    : timestamp.replace(' ', 'T') + 'Z';
  return new Date(ts);
}

export function RecentActivity() {
  const { data, isLoading, error } = useRecentEvents(5);
  const invalidateEvents = useInvalidateEvents();

  // Connect to WebSocket for instant updates
  useWebSocket({
    onNewEvent: () => {
      // New event created - refetch immediately
      invalidateEvents();
    },
    onNotification: () => {
      // Alert notification received - refetch to show updated data
      invalidateEvents();
    },
    onAlert: () => {
      // Alert triggered - refetch to show updated data
      invalidateEvents();
    },
  });

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Activity className="h-5 w-5 text-blue-600" />
            <CardTitle>Recent Activity</CardTitle>
          </div>
          <Link href="/events">
            <Button variant="ghost" size="sm" className="text-blue-600 hover:text-blue-700">
              View all
              <ArrowRight className="ml-1 h-4 w-4" />
            </Button>
          </Link>
        </div>
        <CardDescription>
          Latest events from all cameras
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="flex items-center space-x-3 animate-pulse">
                <div className="w-16 h-12 bg-muted rounded" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 bg-muted rounded w-3/4" />
                  <div className="h-3 bg-muted rounded w-1/2" />
                </div>
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="flex items-center justify-center py-8 text-muted-foreground">
            <AlertCircle className="h-5 w-5 mr-2" />
            <span>Failed to load events</span>
          </div>
        ) : !data?.events?.length ? (
          <div className="text-center py-8">
            <Activity className="h-10 w-10 mx-auto text-muted-foreground mb-3" />
            <p className="text-sm text-muted-foreground">
              No events detected yet
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Events will appear here when motion is detected
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {data.events.map((event) => (
              <Link
                key={event.id}
                href={`/events?highlight=${event.id}`}
                className="flex items-start space-x-3 p-2 rounded-lg hover:bg-muted/50 transition-colors group"
              >
                {/* Thumbnail */}
                {(() => {
                  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
                  // thumbnail_path from DB is already full API path like "/api/v1/thumbnails/2025-11-25/uuid.jpg"
                  const src = event.thumbnail_base64
                    ? event.thumbnail_base64.startsWith('data:')
                      ? event.thumbnail_base64
                      : `data:image/jpeg;base64,${event.thumbnail_base64}`
                    : event.thumbnail_path
                    ? `${apiUrl}${event.thumbnail_path}`
                    : null;

                  return src ? (
                    <img
                      src={src}
                      alt="Event thumbnail"
                      className="w-16 h-12 object-cover rounded flex-shrink-0"
                    />
                  ) : (
                    <div className="w-16 h-12 bg-muted rounded flex items-center justify-center flex-shrink-0">
                      <Camera className="h-5 w-5 text-muted-foreground" />
                    </div>
                  );
                })()}

                {/* Event details */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate group-hover:text-blue-600 transition-colors">
                    {event.description || 'Motion detected'}
                  </p>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground mt-1">
                    <span className="flex items-center">
                      <Clock className="h-3 w-3 mr-1" />
                      {formatDistanceToNow(parseUTCTimestamp(event.timestamp), { addSuffix: true })}
                    </span>
                    {event.objects_detected?.length > 0 && (
                      <span className="flex items-center gap-1">
                        {event.objects_detected.slice(0, 2).map((obj) => (
                          <span
                            key={obj}
                            className="px-1.5 py-0.5 bg-muted rounded text-xs capitalize"
                          >
                            {obj}
                          </span>
                        ))}
                        {event.objects_detected.length > 2 && (
                          <span className="text-muted-foreground">
                            +{event.objects_detected.length - 2}
                          </span>
                        )}
                      </span>
                    )}
                  </div>
                </div>

                {/* Confidence badge */}
                <span className={`text-xs px-2 py-1 rounded-full flex-shrink-0 ${getConfidenceColor(event.confidence)}`}>
                  {event.confidence}%
                </span>
              </Link>
            ))}

            {/* View all link at bottom if there are more events */}
            {data.total_count > 5 && (
              <div className="pt-2 border-t">
                <Link href="/events">
                  <Button variant="outline" size="sm" className="w-full">
                    View all {data.total_count} events
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                </Link>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
