/**
 * EventCard component - displays individual event in timeline
 */

'use client';

import { useState, memo, useCallback } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { Video, ChevronDown, ChevronUp, Images, UserPlus, ArrowRightLeft, User, Car } from 'lucide-react';
import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import type { IEvent, SmartDetectionType } from '@/types/event';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { SourceTypeBadge } from './SourceTypeBadge';
import { SmartDetectionBadge } from './SmartDetectionBadge';
import { CorrelationIndicator } from './CorrelationIndicator';
import { AnalysisModeBadge } from './AnalysisModeBadge';
import { AIProviderBadge } from './AIProviderBadge';
import { ConfidenceIndicator } from './ConfidenceIndicator';
import { ReAnalyzeButton } from './ReAnalyzeButton';
import { ReanalyzedIndicator } from './ReanalyzedIndicator';
import { ReclassifyingIndicator } from './ReclassifyingIndicator';
import { FeedbackButtons } from './FeedbackButtons';
import { AnomalyBadge } from './AnomalyBadge';
import { FrameGalleryModal } from './FrameGalleryModal';
import { VideoPlayerModal } from '@/components/video/VideoPlayerModal';
import { EntitySelectModal } from '@/components/entities/EntitySelectModal';
import { EntityCreateModal } from '@/components/entities/EntityCreateModal';
import { useAssignEventToEntity } from '@/hooks/useEntities';
import { cn } from '@/lib/utils';

interface EventCardProps {
  event: IEvent;
  onClick: () => void;
  /** Story P2-4.4: Callback when a correlated event camera is clicked */
  onCorrelatedEventClick?: (eventId: string) => void;
  /** Story P2-4.4: Whether this card is currently highlighted (from correlation scroll) */
  isHighlighted?: boolean;
  /** Story P3-6.4: Callback when event is re-analyzed */
  onReanalyze?: (updatedEvent: IEvent) => void;
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

export const EventCard = memo(function EventCard({
  event,
  onClick,
  onCorrelatedEventClick,
  isHighlighted = false,
  onReanalyze,
}: EventCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [imageError, setImageError] = useState(false);
  // Story P8-2.2: Frame gallery modal state
  const [frameGalleryOpen, setFrameGalleryOpen] = useState(false);
  // Story P8-3.2: Video player modal state
  const [videoPlayerOpen, setVideoPlayerOpen] = useState(false);
  // Story P9-4.4: Entity select modal state
  const [entityModalOpen, setEntityModalOpen] = useState(false);
  // Story P10-4.2: Entity create modal state (from EntitySelectModal)
  const [entityCreateOpen, setEntityCreateOpen] = useState(false);
  // Story P16-4.3: Re-classification state
  const [isReclassifying, setIsReclassifying] = useState(false);

  // Story P9-4.4: Mutation hook for assigning events to entities
  const assignEventMutation = useAssignEventToEntity();
  const queryClient = useQueryClient();

  // Story P9-4.4: Handle entity selection confirmation
  // Story P16-4.3: Triggers re-classification after successful assignment
  const handleEntitySelect = useCallback(
    async (entityId: string, entityName: string | null) => {
      try {
        const result = await assignEventMutation.mutateAsync({
          eventId: event.id,
          entityId,
        });
        toast.success(result.message);
        setEntityModalOpen(false);

        // Story P16-4.3: Trigger re-classification after successful assignment
        // AC1: Show loading indicator
        setIsReclassifying(true);

        try {
          // Trigger re-analysis with single_frame mode (lowest cost)
          const updatedEvent = await apiClient.events.reanalyze(event.id, 'single_frame');

          // AC2: Show success toast and update event
          toast.success('Event re-classified successfully', {
            description: entityName
              ? `Updated description with "${entityName}" context`
              : 'Updated description with entity context',
          });

          // Invalidate event queries to refresh with new description
          queryClient.invalidateQueries({ queryKey: ['events'] });
          queryClient.invalidateQueries({ queryKey: ['event', event.id] });

          // Call onReanalyze callback if provided
          onReanalyze?.(updatedEvent);
        } catch (reclassifyError) {
          // AC3: Show error toast but keep entity assignment
          console.error('Re-classification failed:', reclassifyError);
          toast.error('Re-classification failed', {
            description: 'Entity was assigned but description could not be updated',
          });
        } finally {
          setIsReclassifying(false);
        }
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : 'Failed to assign event'
        );
      }
    },
    [event.id, assignEventMutation, queryClient, onReanalyze]
  );

  // Story P10-4.2: Handle "Create New" from EntitySelectModal
  const handleCreateNewFromSelect = useCallback(() => {
    setEntityModalOpen(false);
    setEntityCreateOpen(true);
  }, []);

  // Story P10-4.2: Handle entity created - auto-assign to this event
  const handleEntityCreated = useCallback(
    async (entityId: string, entityName: string | null) => {
      setEntityCreateOpen(false);
      // Auto-assign the newly created entity to this event
      await handleEntitySelect(entityId, entityName);
    },
    [handleEntitySelect]
  );

  // Story P2-4.4: Check if event has correlations
  const hasCorrelations = event.correlated_events && event.correlated_events.length > 0;

  // Story P9-4.4: Check if event has entity association
  const hasEntity = !!event.entity_id;

  const eventDate = parseUTCTimestamp(event.timestamp);
  const relativeTime = formatDistanceToNow(eventDate, {
    addSuffix: true,
  });

  // Determine thumbnail source
  // thumbnail_path from DB is already full API path like "/api/v1/thumbnails/2025-11-25/uuid.jpg"
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? '';
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
      className={cn(
        "overflow-hidden cursor-pointer transition-all hover:shadow-md hover:border-blue-300",
        // Story P2-4.4: Visual grouping for correlated events (AC4)
        hasCorrelations && "border-l-4 border-l-blue-400",
        // Story P2-4.4: Highlight animation when scrolled to from correlation link (AC3)
        isHighlighted && "ring-2 ring-blue-500 ring-offset-2 animate-pulse"
      )}
      onClick={onClick}
      data-event-id={event.id}
    >
      <div className="flex flex-col sm:flex-row">
        {/* Thumbnail - Story P8-2.2: Clickable to open frame gallery */}
        <button
          type="button"
          className="relative w-full sm:w-80 h-48 bg-gray-100 flex-shrink-0 group cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-purple-500 focus-visible:ring-offset-2"
          onClick={(e) => {
            e.stopPropagation();
            setFrameGalleryOpen(true);
          }}
          aria-label="View analysis frames"
        >
          {thumbnailSrc && !imageError ? (
            <>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                key={thumbnailSrc}
                src={thumbnailSrc}
                alt="Event thumbnail"
                className="w-full h-full object-cover transition-transform group-hover:scale-[1.02]"
                onError={() => setImageError(true)}
              />
              {/* Hover overlay to indicate clickability */}
              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors flex items-center justify-center">
                <div className="opacity-0 group-hover:opacity-100 transition-opacity bg-black/60 rounded-full p-3">
                  <Images className="w-6 h-6 text-white" />
                </div>
              </div>
            </>
          ) : (
            <div className="absolute inset-0 flex items-center justify-center bg-gray-200">
              <Video className="w-12 h-12 text-gray-400" />
              <span className="sr-only">No thumbnail available</span>
            </div>
          )}
        </button>

        {/* Event Details */}
        <div className="flex-1 p-4 space-y-3">
          {/* Timestamp, Camera, and Source Type */}
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <div className="flex items-center space-x-2">
              <Video className="w-4 h-4" />
              <span>{event.camera_name || `Camera ${event.camera_id.slice(0, 8)}`}</span>
            </div>
            <div className="flex items-center gap-2">
              <time
                dateTime={event.timestamp}
                title={eventDate.toLocaleString()}
                className="font-medium"
              >
                {relativeTime}
              </time>
              {/* Story P3-3.4: Analysis Mode Badge (AC1, AC2, AC3, AC4) */}
              <AnalysisModeBadge
                analysisMode={event.analysis_mode}
                frameCountUsed={event.frame_count_used}
                fallbackReason={event.fallback_reason}
              />
              {/* Story P3-4.5: AI Provider Badge */}
              <AIProviderBadge provider={event.provider_used} />
              {/* Story P3-6.3: AI Confidence Indicator (AC1, AC2, AC3, AC4, AC5, AC6) */}
              <ConfidenceIndicator
                aiConfidence={event.ai_confidence}
                lowConfidence={event.low_confidence}
                vagueReason={event.vague_reason}
              />
              {/* Story P3-6.4: Re-analyzed Indicator (AC7) */}
              <ReanalyzedIndicator reanalyzedAt={event.reanalyzed_at} />
              {/* Story P3-6.4: Re-analyze Button for low confidence events (AC1) */}
              <ReAnalyzeButton
                event={event}
                onReanalyze={onReanalyze}
              />
              {/* Story P4-7.3: Anomaly Badge (AC1) */}
              <AnomalyBadge score={event.anomaly_score} />
              {/* Story P8-3.2: Video indicator (AC2.6, AC2.7) */}
              {event.video_path && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setVideoPlayerOpen(true);
                  }}
                  className="p-1 rounded hover:bg-gray-100 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1"
                  aria-label="Play motion video"
                  title="Watch motion video"
                >
                  <Video className="w-4 h-4 text-blue-600" />
                </button>
              )}
              {event.source_type && (
                <SourceTypeBadge sourceType={event.source_type} />
              )}
            </div>
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
                className="text-xs text-blue-600 hover:text-blue-700 font-medium flex items-center rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1"
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

          {/* Detected Objects */}
          <div className="flex flex-wrap gap-1.5">
            {/* Smart Detection Badge for Protect events */}
            {event.smart_detection_type && (
              <SmartDetectionBadge
                detectionType={event.smart_detection_type as SmartDetectionType}
              />
            )}
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

          {/* Story P2-4.4: Correlation Indicator (AC1, AC2, AC3, AC8) */}
          {hasCorrelations && onCorrelatedEventClick && (
            <CorrelationIndicator
              correlatedEvents={event.correlated_events!}
              onEventClick={onCorrelatedEventClick}
            />
          )}

          {/* Story P9-4.4: Entity badge and assign button (AC-4.4.1, AC-4.4.2, AC-4.4.6) */}
          {/* Story P16-4.3: Re-classification indicator */}
          <div className="flex items-center justify-between mt-2">
            <div className="flex items-center gap-2">
              {/* Story P16-4.3: Show re-classifying indicator (AC1) */}
              <ReclassifyingIndicator isActive={isReclassifying} />
              {/* Entity badge - shows linked entity name */}
              {hasEntity && !isReclassifying && (
                <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
                  {event.objects_detected?.includes('person') ? (
                    <User className="h-3 w-3" />
                  ) : event.objects_detected?.includes('vehicle') ? (
                    <Car className="h-3 w-3" />
                  ) : (
                    <User className="h-3 w-3" />
                  )}
                  {event.entity_name}
                </span>
              )}
              {/* Add to Entity / Move to Entity button */}
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs"
                onClick={(e) => {
                  e.stopPropagation();
                  setEntityModalOpen(true);
                }}
              >
                {hasEntity ? (
                  <>
                    <ArrowRightLeft className="h-3 w-3 mr-1" />
                    Move to Entity
                  </>
                ) : (
                  <>
                    <UserPlus className="h-3 w-3 mr-1" />
                    Add to Entity
                  </>
                )}
              </Button>
            </div>

            {/* Story P4-5.1: Feedback Buttons (AC1, AC2, AC8, AC9, AC10) */}
            {/* Story P9-3.3: Pass smart_detection_type for package feedback */}
            <FeedbackButtons
              eventId={event.id}
              existingFeedback={event.feedback}
              smartDetectionType={event.smart_detection_type}
            />
          </div>
        </div>
      </div>

      {/* Story P9-4.4: Entity Select Modal (AC-4.4.3, AC-4.4.4, AC-4.4.5) */}
      {/* Story P10-4.2: Added onCreateNew callback (AC-4.1.7) */}
      <EntitySelectModal
        open={entityModalOpen}
        onOpenChange={setEntityModalOpen}
        onSelect={handleEntitySelect}
        onCreateNew={handleCreateNewFromSelect}
        title={hasEntity ? 'Move to Entity' : 'Add to Entity'}
        description={
          hasEntity
            ? 'Select a different entity to move this event to'
            : 'Select an entity to associate this event with'
        }
        isLoading={assignEventMutation.isPending}
      />

      {/* Story P10-4.2: Entity Create Modal (triggered from EntitySelectModal) */}
      <EntityCreateModal
        open={entityCreateOpen}
        onOpenChange={setEntityCreateOpen}
        onCreated={handleEntityCreated}
      />

      {/* Story P8-2.2: Frame Gallery Modal (AC2.1 - AC2.8) */}
      <FrameGalleryModal
        eventId={event.id}
        open={frameGalleryOpen}
        onOpenChange={setFrameGalleryOpen}
      />

      {/* Story P8-3.2: Video Player Modal (AC2.7, AC2.8, AC2.9) */}
      <VideoPlayerModal
        open={videoPlayerOpen}
        onOpenChange={setVideoPlayerOpen}
        eventId={event.id}
        cameraName={event.camera_name}
        timestamp={event.timestamp}
      />
    </Card>
  );
});
