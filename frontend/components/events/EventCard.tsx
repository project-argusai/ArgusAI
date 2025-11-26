/**
 * EventCard component - displays individual event in timeline
 */

'use client';

import { useState, memo } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { Video, ChevronDown, ChevronUp } from 'lucide-react';
import type { IEvent } from '@/types/event';
import { getConfidenceColor } from '@/types/event';
import { Card } from '@/components/ui/card';

interface EventCardProps {
  event: IEvent;
  onClick: () => void;
}

const OBJECT_ICONS: Record<string, string> = {
  person: '👤',
  vehicle: '🚗',
  animal: '🐾',
  package: '📦',
  unknown: '❓',
};

// Parse timestamp as UTC (backend stores UTC without timezone indicator)
function parseUTCTimestamp(timestamp: string): Date {
  // If timestamp doesn't have timezone info, append 'Z' to interpret as UTC
  const ts = timestamp.includes('Z') || timestamp.includes('+') || timestamp.includes('-', 10)
    ? timestamp
    : timestamp.replace(' ', 'T') + 'Z';
  return new Date(ts);
}

export const EventCard = memo(function EventCard({ event, onClick }: EventCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [imageError, setImageError] = useState(false);

  const eventDate = parseUTCTimestamp(event.timestamp);
  const relativeTime = formatDistanceToNow(eventDate, {
    addSuffix: true,
  });

  const confidenceColorClass = getConfidenceColor(event.confidence);

  // Determine thumbnail source
  // thumbnail_path from DB is already full API path like "/api/v1/thumbnails/2025-11-25/uuid.jpg"
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  const thumbnailSrc = event.thumbnail_base64
    ? `data:image/jpeg;base64,${event.thumbnail_base64}`
    : event.thumbnail_path
    ? `${apiUrl}${event.thumbnail_path}`
    : null;


  // Truncate description to 3 lines (~150 chars)
  const MAX_LENGTH = 150;
  const isTruncated = event.description.length > MAX_LENGTH;
  const displayDescription = !isExpanded && isTruncated
    ? event.description.slice(0, MAX_LENGTH) + '...'
    : event.description;

  return (
    <Card
      className="overflow-hidden cursor-pointer transition-all hover:shadow-md hover:border-blue-300"
      onClick={onClick}
    >
      <div className="flex flex-col sm:flex-row">
        {/* Thumbnail */}
        <div className="relative w-full sm:w-80 h-48 bg-gray-100 flex-shrink-0">
          {thumbnailSrc && !imageError ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={thumbnailSrc}
              src={thumbnailSrc}
              alt="Event thumbnail"
              className="w-full h-full object-cover"
              onError={(e) => {
                console.error('Image load failed:', thumbnailSrc, e);
                setImageError(true);
              }}
              onLoad={() => console.log('Image loaded successfully:', thumbnailSrc)}
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center bg-gray-200">
              <Video className="w-12 h-12 text-gray-400" />
              <span className="sr-only">No thumbnail available</span>
            </div>
          )}
        </div>

        {/* Event Details */}
        <div className="flex-1 p-4 space-y-3">
          {/* Timestamp and Camera */}
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <div className="flex items-center space-x-2">
              <Video className="w-4 h-4" />
              <span>Camera {event.camera_id.slice(0, 8)}</span>
            </div>
            <time
              dateTime={event.timestamp}
              title={eventDate.toLocaleString()}
              className="font-medium"
            >
              {relativeTime}
            </time>
          </div>

          {/* Description */}
          <div className="space-y-1">
            <p className="text-sm leading-relaxed">{displayDescription}</p>
            {isTruncated && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setIsExpanded(!isExpanded);
                }}
                className="text-xs text-blue-600 hover:text-blue-700 font-medium flex items-center"
              >
                {isExpanded ? (
                  <>
                    Show less <ChevronUp className="w-3 h-3 ml-1" />
                  </>
                ) : (
                  <>
                    Read more <ChevronDown className="w-3 h-3 ml-1" />
                  </>
                )}
              </button>
            )}
          </div>

          {/* Confidence and Objects */}
          <div className="flex items-center justify-between flex-wrap gap-2">
            {/* Detected Objects */}
            <div className="flex flex-wrap gap-1.5">
              {event.objects_detected.map((obj, idx) => (
                <span
                  key={idx}
                  className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-700"
                >
                  <span className="mr-1">{OBJECT_ICONS[obj] || OBJECT_ICONS.unknown}</span>
                  {obj.charAt(0).toUpperCase() + obj.slice(1)}
                </span>
              ))}
            </div>

            {/* Confidence Score */}
            <div
              className={`px-2.5 py-1 rounded-full text-xs font-semibold ${confidenceColorClass}`}
            >
              {event.confidence}% confident
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
});
