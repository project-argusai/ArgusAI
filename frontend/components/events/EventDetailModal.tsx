/**
 * EventDetailModal component - detailed view of a single event
 */

'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';
import { formatDistanceToNow } from 'date-fns';
import {
  X,
  Trash2,
  Camera,
  Calendar,
  Tag,
  Gauge,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
  Video,
  Link2,
  Sparkles,
  Zap,
  MessageCircle,
  Sparkle,
} from 'lucide-react';
import type { IEvent } from '@/types/event';
import { getConfidenceColor, getConfidenceLevel } from '@/types/event';
import { useDeleteEvent } from '@/lib/hooks/useEvents';
import { KeyFramesGallery } from './KeyFramesGallery';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
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
import { Button } from '@/components/ui/button';

// Parse timestamp as UTC (backend stores UTC without timezone indicator)
function parseUTCTimestamp(timestamp: string): Date {
  // If timestamp doesn't have timezone info, append 'Z' to interpret as UTC
  const ts = timestamp.includes('Z') || timestamp.includes('+') || timestamp.includes('-', 10)
    ? timestamp
    : timestamp.replace(' ', 'T') + 'Z';
  return new Date(ts);
}

interface EventDetailModalProps {
  event: IEvent | null;
  open: boolean;
  onClose: () => void;
  allEvents?: IEvent[];
  onNavigate?: (event: IEvent) => void;
}

const OBJECT_ICONS: Record<string, string> = {
  person: '👤',
  vehicle: '🚗',
  animal: '🐾',
  package: '📦',
  unknown: '❓',
};

export function EventDetailModal({
  event,
  open,
  onClose,
  allEvents = [],
  onNavigate,
}: EventDetailModalProps) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [imageError, setImageError] = useState(false);
  const deleteEvent = useDeleteEvent();

  // Navigation
  const currentIndex = event ? allEvents.findIndex((e) => e.id === event.id) : -1;
  const hasPrev = currentIndex > 0;
  const hasNext = currentIndex < allEvents.length - 1;

  const handlePrev = () => {
    if (hasPrev && onNavigate && event) {
      onNavigate(allEvents[currentIndex - 1]);
    }
  };

  const handleNext = () => {
    if (hasNext && onNavigate && event) {
      onNavigate(allEvents[currentIndex + 1]);
    }
  };

  // Reset image error when event changes
  useEffect(() => {
    setImageError(false);
  }, [event?.id]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!open) return;

      switch (e.key) {
        case 'ArrowLeft':
          e.preventDefault();
          handlePrev();
          break;
        case 'ArrowRight':
          e.preventDefault();
          handleNext();
          break;
        case 'Escape':
          e.preventDefault();
          onClose();
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, currentIndex, allEvents.length]);

  if (!event) return null;

  // Handle delete
  const handleDelete = async () => {
    try {
      await deleteEvent.mutateAsync(event.id);
      setShowDeleteConfirm(false);
      onClose();
    } catch (error) {
      console.error('Failed to delete event:', error);
    }
  };

  const eventDate = parseUTCTimestamp(event.timestamp);
  const relativeTime = formatDistanceToNow(eventDate, {
    addSuffix: true,
  });

  const confidenceColorClass = getConfidenceColor(event.confidence);
  const confidenceLevel = getConfidenceLevel(event.confidence);

  // Determine image source
  // thumbnail_path from DB is already full API path like "/api/v1/thumbnails/2025-11-25/uuid.jpg"
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  const imageSrc = event.thumbnail_base64
    ? `data:image/jpeg;base64,${event.thumbnail_base64}`
    : event.thumbnail_path
    ? `${apiUrl}${event.thumbnail_path}`
    : null;

  return (
    <>
      <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <DialogTitle className="text-2xl">Event Details</DialogTitle>
                <DialogDescription className="mt-2">
                  <time
                    dateTime={event.timestamp}
                    title={eventDate.toLocaleString()}
                    className="text-sm font-medium"
                  >
                    {relativeTime}
                  </time>
                </DialogDescription>
              </div>

              {/* Navigation Buttons */}
              {allEvents.length > 1 && (
                <div className="flex items-center gap-2 ml-4">
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={handlePrev}
                    disabled={!hasPrev}
                    aria-label="Previous event"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </Button>
                  <span className="text-sm text-muted-foreground">
                    {currentIndex + 1} / {allEvents.length}
                  </span>
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={handleNext}
                    disabled={!hasNext}
                    aria-label="Next event"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </div>
              )}
            </div>
          </DialogHeader>

          {/* Image/Thumbnail */}
          <div className="relative w-full h-96 bg-gray-100 rounded-lg overflow-hidden">
            {imageSrc && !imageError ? (
              <Image
                src={imageSrc}
                alt="Event image"
                fill
                className="object-contain"
                onError={() => setImageError(true)}
                unoptimized={imageSrc.startsWith('http://localhost') || imageSrc.startsWith('data:')}
                priority
              />
            ) : (
              <div className="absolute inset-0 flex items-center justify-center bg-gray-200">
                <Video className="w-16 h-16 text-gray-400" />
                <span className="sr-only">No image available</span>
              </div>
            )}
          </div>

          {/* Description */}
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-gray-700">Description</h3>
            <p className="text-base leading-relaxed">{event.description}</p>
          </div>

          {/* Metadata Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t">
            {/* Camera */}
            <div className="flex items-start space-x-3">
              <Camera className="w-5 h-5 text-gray-500 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-gray-700">Camera</p>
                <p className="text-sm text-gray-600">{event.camera_id.slice(0, 8)}</p>
              </div>
            </div>

            {/* Timestamp */}
            <div className="flex items-start space-x-3">
              <Calendar className="w-5 h-5 text-gray-500 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-gray-700">Captured</p>
                <p className="text-sm text-gray-600">
                  {eventDate.toLocaleString()}
                </p>
              </div>
            </div>

            {/* Objects Detected */}
            <div className="flex items-start space-x-3">
              <Tag className="w-5 h-5 text-gray-500 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-gray-700 mb-1">Objects Detected</p>
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
              </div>
            </div>

            {/* Confidence Score */}
            <div className="flex items-start space-x-3">
              <Gauge className="w-5 h-5 text-gray-500 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-gray-700">Confidence</p>
                <div className="flex items-center gap-2">
                  <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${confidenceColorClass}`}>
                    {event.confidence}%
                  </span>
                  <span className="text-sm text-gray-600 capitalize">
                    ({confidenceLevel})
                  </span>
                </div>
              </div>
            </div>

            {/* Story P3-4.5: AI Provider (AC3) */}
            {event.provider_used && (
              <div className="flex items-start space-x-3">
                {event.provider_used === 'openai' && <Sparkles className="w-5 h-5 text-green-500 mt-0.5" />}
                {event.provider_used === 'grok' && <Zap className="w-5 h-5 text-orange-500 mt-0.5" />}
                {event.provider_used === 'claude' && <MessageCircle className="w-5 h-5 text-amber-500 mt-0.5" />}
                {event.provider_used === 'gemini' && <Sparkle className="w-5 h-5 text-blue-500 mt-0.5" />}
                <div>
                  <p className="text-sm font-medium text-gray-700">AI Provider</p>
                  <p className="text-sm text-gray-600">
                    {event.provider_used === 'openai' && 'OpenAI GPT-4o mini'}
                    {event.provider_used === 'grok' && 'xAI Grok 2 Vision'}
                    {event.provider_used === 'claude' && 'Anthropic Claude 3 Haiku'}
                    {event.provider_used === 'gemini' && 'Google Gemini 2.0 Flash'}
                  </p>
                </div>
              </div>
            )}

            {/* Alert Status */}
            {event.alert_triggered && (
              <div className="flex items-start space-x-3 md:col-span-2">
                <AlertTriangle className="w-5 h-5 text-orange-500 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-gray-700">Alert Status</p>
                  <p className="text-sm text-orange-600">Alert was triggered for this event</p>
                </div>
              </div>
            )}
          </div>

          {/* Story P2-4.4: Related Events Section (AC5, AC6) */}
          {event.correlated_events && event.correlated_events.length > 0 && (
            <div className="space-y-3 pt-4 border-t">
              <div className="flex items-center gap-2">
                <Link2 className="w-5 h-5 text-blue-500" />
                <h3 className="text-sm font-semibold text-gray-700">Related Events</h3>
                <span className="text-xs text-muted-foreground">
                  ({event.correlated_events.length} other camera{event.correlated_events.length > 1 ? 's' : ''})
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {event.correlated_events.map((relatedEvent) => {
                  const relatedDate = parseUTCTimestamp(relatedEvent.timestamp);
                  const relatedRelativeTime = formatDistanceToNow(relatedDate, { addSuffix: true });

                  // Build full thumbnail URL
                  const relatedThumbnailSrc = relatedEvent.thumbnail_url
                    ? `${apiUrl}${relatedEvent.thumbnail_url}`
                    : null;

                  // Find the full event object in allEvents to navigate to
                  const fullRelatedEvent = allEvents.find((e) => e.id === relatedEvent.id);

                  return (
                    <button
                      key={relatedEvent.id}
                      type="button"
                      onClick={() => {
                        if (fullRelatedEvent && onNavigate) {
                          onNavigate(fullRelatedEvent);
                        }
                      }}
                      className="group flex flex-col rounded-lg border border-gray-200 overflow-hidden hover:border-blue-400 hover:shadow-md transition-all focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                      disabled={!fullRelatedEvent}
                    >
                      {/* Thumbnail */}
                      <div className="relative w-full h-24 bg-gray-100">
                        {relatedThumbnailSrc ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={relatedThumbnailSrc}
                            alt={`Event from ${relatedEvent.camera_name}`}
                            className="w-full h-full object-cover group-hover:opacity-90 transition-opacity"
                          />
                        ) : (
                          <div className="absolute inset-0 flex items-center justify-center bg-gray-200">
                            <Video className="w-8 h-8 text-gray-400" />
                          </div>
                        )}
                      </div>

                      {/* Info */}
                      <div className="p-2 text-left">
                        <p className="text-xs font-medium text-gray-800 truncate">
                          {relatedEvent.camera_name}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {relatedRelativeTime}
                        </p>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Story P3-7.5: Key Frames Gallery for multi-frame analysis */}
          {event.key_frames_base64 && event.key_frames_base64.length > 0 && (
            <KeyFramesGallery
              frames={event.key_frames_base64}
              timestamps={event.frame_timestamps || []}
            />
          )}

          <DialogFooter className="flex-col sm:flex-row gap-2">
            <Button
              variant="destructive"
              onClick={() => setShowDeleteConfirm(true)}
              disabled={deleteEvent.isPending}
            >
              <Trash2 className="w-4 h-4 mr-2" />
              Delete Event
            </Button>
            <Button variant="outline" onClick={onClose}>
              <X className="w-4 h-4 mr-2" />
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Event?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. This will permanently delete this event and its
              associated data.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-red-600 hover:bg-red-700"
              disabled={deleteEvent.isPending}
            >
              {deleteEvent.isPending ? 'Deleting...' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
