/**
 * DoorbellEventCard component - displays doorbell ring events with distinct styling
 *
 * Story P2-4.2: Doorbell events have special visual treatment:
 * - Header with bell icon and "DOORBELL RING" label
 * - Cyan left border accent (3px)
 * - Camera name shown below header
 * - Relative time formatting
 * - Person badge always shown when person detected
 */

'use client';

import { useState, memo } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { Bell, Video, ChevronDown, ChevronUp } from 'lucide-react';
import type { IEvent } from '@/types/event';
import { Card } from '@/components/ui/card';

interface DoorbellEventCardProps {
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
  const ts = timestamp.includes('Z') || timestamp.includes('+') || timestamp.includes('-', 10)
    ? timestamp
    : timestamp.replace(' ', 'T') + 'Z';
  return new Date(ts);
}

// Format relative time with "Just now" for very recent events
function formatRelativeTime(date: Date): string {
  const now = new Date();
  const diffSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (diffSeconds < 60) {
    return 'Just now';
  }

  return formatDistanceToNow(date, { addSuffix: true });
}

export const DoorbellEventCard = memo(function DoorbellEventCard({
  event,
  onClick,
}: DoorbellEventCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [imageError, setImageError] = useState(false);

  const eventDate = parseUTCTimestamp(event.timestamp);
  const relativeTime = formatRelativeTime(eventDate);

  // Determine thumbnail source
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  const thumbnailSrc = event.thumbnail_base64
    ? `data:image/jpeg;base64,${event.thumbnail_base64}`
    : event.thumbnail_path
    ? `${apiUrl}${event.thumbnail_path}`
    : null;

  // Truncate description to 3 lines (~150 chars)
  const MAX_LENGTH = 150;
  const isTruncated = event.description.length > MAX_LENGTH;
  const displayDescription =
    !isExpanded && isTruncated
      ? event.description.slice(0, MAX_LENGTH) + '...'
      : event.description;

  // Check if person was detected
  const hasPersonDetected = event.objects_detected.includes('person');

  return (
    <Card
      className="overflow-hidden cursor-pointer transition-all hover:shadow-md hover:border-cyan-400 border-l-4 border-l-cyan-500"
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
              alt="Doorbell event thumbnail"
              className="w-full h-full object-cover"
              onError={() => setImageError(true)}
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center bg-gray-200">
              <Bell className="w-12 h-12 text-cyan-400" />
              <span className="sr-only">No thumbnail available</span>
            </div>
          )}
        </div>

        {/* Event Details */}
        <div className="flex-1 p-4 space-y-3">
          {/* Doorbell Ring Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bell className="w-5 h-5 text-cyan-500" aria-hidden="true" />
              <span className="text-sm font-bold text-cyan-700 uppercase tracking-wide">
                Doorbell Ring
              </span>
            </div>
            <time
              dateTime={event.timestamp}
              title={eventDate.toLocaleString()}
              className="text-sm font-medium text-muted-foreground"
            >
              {relativeTime}
            </time>
          </div>

          {/* Camera Name */}
          <div className="flex items-center text-sm text-muted-foreground">
            <Video className="w-4 h-4 mr-1" />
            <span>Camera {event.camera_id.slice(0, 8)}</span>
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
                className="text-xs text-cyan-600 hover:text-cyan-700 font-medium flex items-center rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500 focus-visible:ring-offset-1"
                aria-expanded={isExpanded}
                aria-label={isExpanded ? 'Show less of description' : 'Read more of description'}
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

          {/* Detected Objects - Always show Person first if detected */}
          <div className="flex flex-wrap gap-1.5">
            {hasPersonDetected && (
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                <span className="mr-1">{OBJECT_ICONS.person}</span>
                Person
              </span>
            )}
            {event.objects_detected
              .filter((obj) => obj !== 'person')
              .map((obj, idx) => (
                <span
                  key={idx}
                  className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-700"
                >
                  <span className="mr-1">{OBJECT_ICONS[obj] || OBJECT_ICONS.unknown}</span>
                  {obj.charAt(0).toUpperCase() + obj.slice(1)}
                </span>
              ))}
          </div>
        </div>
      </div>
    </Card>
  );
});
