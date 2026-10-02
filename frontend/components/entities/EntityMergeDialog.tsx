/**
 * EntityMergeDialog component - confirmation dialog for merging two entities (Story P9-4.5)
 * AC-4.5.3: Dialog shows both entities with event counts
 * AC-4.5.4: Can choose which entity to keep
 * AC-4.5.7: Toast "Entities merged successfully"
 */

'use client';

import { useState, useEffect } from 'react';
import { Loader2, Merge, User, Car, HelpCircle, AlertTriangle } from 'lucide-react';
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
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
import { useMergeEntities } from '@/hooks/useEntities';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { getEntityDisplayName } from '@/lib/entity-display-name';
import type { IEntity } from '@/types/entity';

interface EntityMergeDialogProps {
  /** Entities to merge [entity1, entity2] */
  entities: [IEntity, IEntity] | null;
  /** Whether the dialog is open */
  open: boolean;
  /** Callback when dialog is closed/cancelled */
  onClose: () => void;
  /** Callback after successful merge */
  onMerged?: () => void;
}

/**
 * Get icon for entity type
 */
function getEntityTypeIcon(entityType: string) {
  switch (entityType) {
    case 'person':
      return <User className="h-5 w-5" />;
    case 'vehicle':
      return <Car className="h-5 w-5" />;
    default:
      return <HelpCircle className="h-5 w-5" />;
  }
}

/**
 * Entity preview card for merge dialog
 */
function EntityPreview({
  entity,
  isSelected,
  onClick,
}: {
  entity: IEntity;
  isSelected: boolean;
  onClick: () => void;
}) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? '';
  const thumbnailUrl = entity.thumbnail_path
    ? entity.thumbnail_path.startsWith('http')
      ? entity.thumbnail_path
      : `${apiUrl}${entity.thumbnail_path}`
    : null;

  const displayName = getEntityDisplayName(entity);

  return (
    <div
      className={cn(
        'border rounded-lg p-4 cursor-pointer transition-all',
        isSelected
          ? 'ring-2 ring-primary border-primary bg-primary/5'
          : 'hover:border-primary/50'
      )}
      onClick={onClick}
    >
      {/* Thumbnail */}
      <div className="w-full h-24 bg-gray-100 rounded-md mb-3 flex items-center justify-center overflow-hidden">
        {thumbnailUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={thumbnailUrl}
            alt={displayName}
            className="w-full h-full object-cover"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = 'none';
            }}
          />
        ) : (
          <div className="text-gray-400">
            {getEntityTypeIcon(entity.entity_type)}
          </div>
        )}
      </div>

      {/* Radio button and name */}
      <div className="flex items-center gap-2 mb-2">
        <RadioGroupItem value={entity.id} id={entity.id} />
        <Label htmlFor={entity.id} className="font-medium truncate cursor-pointer">
          {displayName}
        </Label>
      </div>

      {/* Stats */}
      <div className="text-sm text-muted-foreground space-y-1">
        <p className="capitalize flex items-center gap-1">
          {getEntityTypeIcon(entity.entity_type)}
          {entity.entity_type}
        </p>
        <p>{entity.occurrence_count} event{entity.occurrence_count !== 1 ? 's' : ''}</p>
      </div>
    </div>
  );
}

/**
 * Confirmation dialog for merging two entities
 */
export function EntityMergeDialog({
  entities,
  open,
  onClose,
  onMerged,
}: EntityMergeDialogProps) {
  const mergeMutation = useMergeEntities();

  // Default to entity with more occurrences as primary
  const [primaryEntityId, setPrimaryEntityId] = useState<string>('');

  // Reset selection when entities change
  useEffect(() => {
    if (entities) {
      const [e1, e2] = entities;
      // Default to entity with more occurrences
      setPrimaryEntityId(
        e1.occurrence_count >= e2.occurrence_count ? e1.id : e2.id
      );
    }
  }, [entities]);

  if (!entities) return null;

  const [entity1, entity2] = entities;
  const primaryEntity = entities.find((e) => e.id === primaryEntityId);
  const secondaryEntity = entities.find((e) => e.id !== primaryEntityId);

  const handleMerge = async () => {
    if (!primaryEntity || !secondaryEntity) return;

    try {
      const result = await mergeMutation.mutateAsync({
        primaryEntityId: primaryEntity.id,
        secondaryEntityId: secondaryEntity.id,
      });

      toast.success(result.message || 'Entities merged successfully');
      onMerged?.();
      onClose();
    } catch (error) {
      if (error instanceof Error) {
        toast.error(error.message || 'Failed to merge entities');
      } else {
        toast.error('Failed to merge entities');
      }
    }
  };

  const primaryName = primaryEntity ? getEntityDisplayName(primaryEntity) : 'Unknown';
  const secondaryName = secondaryEntity ? getEntityDisplayName(secondaryEntity) : 'Unknown';

  return (
    <AlertDialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <AlertDialogContent className="max-w-lg">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <Merge className="h-5 w-5 text-primary" />
            Merge Entities
          </AlertDialogTitle>
          <AlertDialogDescription className="space-y-4">
            <p>
              Select which entity to keep. All events from the other entity will be
              moved to the selected one.
            </p>

            {/* Entity Selection */}
            <RadioGroup
              value={primaryEntityId}
              onValueChange={setPrimaryEntityId}
              className="grid grid-cols-2 gap-4"
            >
              <EntityPreview
                entity={entity1}
                isSelected={primaryEntityId === entity1.id}
                onClick={() => setPrimaryEntityId(entity1.id)}
              />
              <EntityPreview
                entity={entity2}
                isSelected={primaryEntityId === entity2.id}
                onClick={() => setPrimaryEntityId(entity2.id)}
              />
            </RadioGroup>

            {/* Warning */}
            <div className="bg-yellow-50 dark:bg-yellow-950/50 border border-yellow-200 dark:border-yellow-900 rounded-md p-3 text-sm text-yellow-800 dark:text-yellow-200 flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 mt-0.5 flex-shrink-0" />
              <div>
                <strong>This action cannot be undone.</strong>
                <p className="mt-1">
                  {secondaryEntity?.occurrence_count || 0} event(s) will be moved
                  from <strong>{secondaryName}</strong> to <strong>{primaryName}</strong>.
                  The entity <strong>{secondaryName}</strong> will be permanently deleted.
                </p>
              </div>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>

        <AlertDialogFooter>
          <AlertDialogCancel disabled={mergeMutation.isPending}>
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={handleMerge}
            disabled={mergeMutation.isPending || !primaryEntityId}
          >
            {mergeMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Merging...
              </>
            ) : (
              <>
                <Merge className="h-4 w-4 mr-2" />
                Merge Entities
              </>
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
