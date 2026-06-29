/**
 * EntityCard component - displays individual entity in the entities list (Story P4-3.6)
 * Shows thumbnail, name, type badge, occurrence count, and timestamps
 * Story P7-4.2: Add "Add Alert" button (AC3, AC4)
 * Story P7-4.3: Open EntityAlertModal when "Add Alert" clicked (AC1)
 * Story P9-4.5: Add checkbox for multi-select merge functionality
 * Story P16-3.3: Add Edit button to open EntityEditModal
 */

'use client';

import { memo, useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { User, Car, HelpCircle, Bell, Check, Pencil } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { EntityAlertModal } from './EntityAlertModal';
import { EntityEditModal, type EntityEditData } from './EntityEditModal';
import type { IEntity } from '@/types/entity';
import { parseApiDate } from '@/lib/datetime';

interface EntityCardProps {
  entity: IEntity;
  /** Thumbnail URL from the most recent event */
  thumbnailUrl?: string | null;
  onClick: () => void;
  /** Story P9-4.5: Whether selection mode is enabled */
  selectable?: boolean;
  /** Story P9-4.5: Whether this card is currently selected */
  isSelected?: boolean;
  /** Story P9-4.5: Callback when selection checkbox is toggled */
  onSelect?: () => void;
  /** Story P9-4.5: Whether selection is disabled (max 2 selected) */
  selectionDisabled?: boolean;
  /** Story P16-3.3: Callback when entity is updated via edit modal */
  onEntityUpdated?: () => void;
}

/**
 * Get icon for entity type
 */
function getEntityTypeIcon(entityType: string) {
  switch (entityType) {
    case 'person':
      return <User className="h-3.5 w-3.5" />;
    case 'vehicle':
      return <Car className="h-3.5 w-3.5" />;
    default:
      return <HelpCircle className="h-3.5 w-3.5" />;
  }
}

/**
 * Get badge variant for entity type
 */
function getEntityTypeBadgeVariant(entityType: string): 'default' | 'secondary' | 'outline' {
  switch (entityType) {
    case 'person':
      return 'default';
    case 'vehicle':
      return 'secondary';
    default:
      return 'outline';
  }
}

export const EntityCard = memo(function EntityCard({
  entity,
  thumbnailUrl,
  onClick,
  selectable = false,
  isSelected = false,
  onSelect,
  selectionDisabled = false,
  onEntityUpdated,
}: EntityCardProps) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? '';

  // Story P7-4.3: Modal state for EntityAlertModal (AC1)
  const [isAlertModalOpen, setIsAlertModalOpen] = useState(false);

  // Story P16-3.3: Modal state for EntityEditModal
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);

  // Story P7-4.3 AC1: "Add Alert" button opens modal
  const handleAddAlert = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent card click from triggering
    setIsAlertModalOpen(true);
  };

  // Story P16-3.3 AC2, AC3: Edit button opens EntityEditModal
  const handleEdit = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent card click from triggering (AC3)
    setIsEditModalOpen(true);
  };

  // Story P9-4.5: Handle checkbox click
  const handleSelectClick = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent card click from triggering
    if (onSelect && !selectionDisabled) {
      onSelect();
    }
  };

  // Build full thumbnail URL if path is relative
  const fullThumbnailUrl = thumbnailUrl
    ? thumbnailUrl.startsWith('http')
      ? thumbnailUrl
      : `${apiUrl}${thumbnailUrl}`
    : null;

  const firstSeenDate = parseApiDate(entity.first_seen_at)!;
  const lastSeenDate = parseApiDate(entity.last_seen_at)!;
  const lastSeenRelative = formatDistanceToNow(lastSeenDate, { addSuffix: true });

  // Display name with fallback
  const displayName = entity.name || `Unknown ${entity.entity_type}`;
  const isNamed = !!entity.name;

  return (
    <Card
      className={cn(
        'overflow-hidden cursor-pointer transition-all hover:shadow-md',
        'flex flex-col',
        isSelected
          ? 'ring-2 ring-primary border-primary bg-primary/5'
          : 'hover:border-blue-300'
      )}
      onClick={onClick}
    >
      {/* Thumbnail Section */}
      <div className="relative w-full h-40 bg-gray-100">
        {/* Story P9-4.5: Selection Checkbox */}
        {selectable && (
          <div
            className="absolute top-2 left-2 z-10"
            onClick={handleSelectClick}
          >
            <div
              className={cn(
                'w-6 h-6 rounded-md border-2 flex items-center justify-center transition-colors',
                isSelected
                  ? 'bg-primary border-primary text-primary-foreground'
                  : selectionDisabled
                    ? 'bg-muted border-muted-foreground/30 cursor-not-allowed'
                    : 'bg-white/80 border-gray-400 hover:border-primary hover:bg-primary/10'
              )}
            >
              {isSelected && <Check className="h-4 w-4" />}
            </div>
          </div>
        )}
        {fullThumbnailUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={fullThumbnailUrl}
            alt={`${displayName} thumbnail`}
            className="w-full h-full object-cover"
            onError={(e) => {
              // Hide broken image
              (e.target as HTMLImageElement).style.display = 'none';
            }}
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-200">
            {entity.entity_type === 'person' ? (
              <User className="w-12 h-12 text-gray-400" />
            ) : entity.entity_type === 'vehicle' ? (
              <Car className="w-12 h-12 text-gray-400" />
            ) : (
              <HelpCircle className="w-12 h-12 text-gray-400" />
            )}
          </div>
        )}

        {/* Entity Type Badge - positioned in corner */}
        <div className="absolute top-2 right-2">
          <Badge variant={getEntityTypeBadgeVariant(entity.entity_type)} className="gap-1">
            {getEntityTypeIcon(entity.entity_type)}
            <span className="capitalize">{entity.entity_type}</span>
          </Badge>
        </div>
      </div>

      {/* Entity Details */}
      <div className="p-4 space-y-2">
        {/* Name */}
        <h3 className={cn(
          'font-medium text-base truncate',
          !isNamed && 'text-muted-foreground italic'
        )}>
          {displayName}
        </h3>

        {/* Occurrence count */}
        <p className="text-sm text-muted-foreground">
          Seen {entity.occurrence_count} time{entity.occurrence_count !== 1 ? 's' : ''}
        </p>

        {/* Timestamps */}
        <div className="text-xs text-muted-foreground space-y-1">
          <p>Last seen: {lastSeenRelative}</p>
          <p>First seen: {firstSeenDate.toLocaleDateString()}</p>
        </div>

        {/* Story P7-4.3 AC1 & P16-3.3: Action buttons */}
        <div className="pt-2 flex gap-2">
          {/* Story P16-3.3: Edit button with tooltip (AC1, AC4) */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={handleEdit}
                aria-label={`Edit ${displayName}`}
              >
                <Pencil className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              <p>Edit entity</p>
            </TooltipContent>
          </Tooltip>

          {/* Story P7-4.3 AC1: Add Alert button */}
          <Button
            variant="outline"
            size="sm"
            className="flex-1 gap-2"
            onClick={handleAddAlert}
            aria-label={`Add alert for ${displayName}`}
          >
            <Bell className="h-4 w-4" />
            Add Alert
          </Button>
        </div>
      </div>

      {/* Story P7-4.3: Entity Alert Modal */}
      <EntityAlertModal
        isOpen={isAlertModalOpen}
        onClose={() => setIsAlertModalOpen(false)}
        entity={entity}
      />

      {/* Story P16-3.3: Entity Edit Modal */}
      <EntityEditModal
        open={isEditModalOpen}
        onOpenChange={setIsEditModalOpen}
        entity={{
          id: entity.id,
          entity_type: entity.entity_type,
          name: entity.name,
          thumbnail_path: entity.thumbnail_path,
        } as EntityEditData}
        onUpdated={onEntityUpdated}
      />
    </Card>
  );
});
