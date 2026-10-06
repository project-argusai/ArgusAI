/**
 * EventEntities - entity chips plus the add flow for one event (issue #652).
 *
 * An event can belong to several entities (a person and their car). Each
 * entity is a chip with its own remove button. "Add to Entity" adds a link
 * and keeps the others; the picker hides entities already on the event.
 * After an add, the event is re-classified so the description can use the
 * new name (Story P16-4.3).
 */

'use client';

import { useCallback, useMemo, useState } from 'react';
import { Car, HelpCircle, User, UserPlus, X } from 'lucide-react';
import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import type { IEvent, IEventEntity } from '@/types/event';
import { MAX_ENTITIES_PER_EVENT } from '@/types/event';
import { Button } from '@/components/ui/button';
import { EntitySelectModal } from '@/components/entities/EntitySelectModal';
import { EntityCreateModal } from '@/components/entities/EntityCreateModal';
import { useAssignEventToEntity, useUnlinkEvent } from '@/hooks/useEntities';
import { getEntityDisplayName } from '@/lib/entity-display-name';
import { applyReanalyzedEvent } from '@/lib/reanalyzed-event';
import { cn } from '@/lib/utils';
import { ReclassifyingIndicator } from './ReclassifyingIndicator';

/**
 * Entities to show for an event. Uses `entities` when the API sent it and
 * falls back to the legacy single-entity fields (older payloads, live
 * WebSocket events).
 */
export function eventEntitiesOf(event: IEvent): IEventEntity[] {
  if (Array.isArray(event.entities)) {
    return event.entities
      .filter((entity) => entity && entity.id !== undefined && entity.id !== null)
      .map((entity) => ({ ...entity, id: String(entity.id) }));
  }
  if (event.entity_id) {
    return [
      {
        id: String(event.entity_id),
        name: event.entity_name ?? null,
        entity_type: event.entity_type ?? 'unknown',
        vehicle_color: event.entity_vehicle_color,
        vehicle_make: event.entity_vehicle_make,
        vehicle_model: event.entity_vehicle_model,
        vehicle_signature: event.entity_vehicle_signature,
        is_primary: true,
        linked: true,
      },
    ];
  }
  return [];
}

function EntityIcon({ entityType }: { entityType: string }) {
  if (entityType === 'vehicle') return <Car className="h-3 w-3" aria-hidden="true" />;
  if (entityType === 'person') return <User className="h-3 w-3" aria-hidden="true" />;
  return <HelpCircle className="h-3 w-3" aria-hidden="true" />;
}

interface EventEntityChipsProps {
  entities: IEventEntity[];
  onRemove?: (entity: IEventEntity) => void;
  removingId?: string | null;
  disabled?: boolean;
}

/** Chips for the entities on an event. Each chip can be removed on its own. */
export function EventEntityChips({
  entities,
  onRemove,
  removingId = null,
  disabled = false,
}: EventEntityChipsProps) {
  if (entities.length === 0) return null;
  return (
    <ul className="flex flex-wrap items-center gap-1.5" aria-label="Entities on this event">
      {entities.map((entity) => {
        const label = getEntityDisplayName(entity);
        const isRemoving = removingId === entity.id;
        return (
          <li
            key={entity.id}
            data-testid="event-entity-chip"
            data-entity-id={entity.id}
            title={entity.is_primary ? `${label} (primary)` : label}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full py-1 pl-2 text-xs font-medium',
              onRemove ? 'pr-1' : 'pr-2',
              entity.entity_type === 'vehicle'
                ? 'bg-green-100 text-green-800'
                : 'bg-blue-100 text-blue-700',
              isRemoving && 'opacity-50'
            )}
          >
            <EntityIcon entityType={entity.entity_type} />
            <span>{label}</span>
            {onRemove && (
              <button
                type="button"
                className="rounded-full p-0.5 hover:bg-black/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:cursor-not-allowed"
                aria-label={`Remove ${label} from this event`}
                disabled={disabled || isRemoving}
                onClick={(e) => {
                  e.stopPropagation();
                  onRemove(entity);
                }}
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}

interface EventEntitiesProps {
  event: IEvent;
  /** Called with the re-analyzed event after an add triggers re-classification */
  onReanalyze?: (updatedEvent: IEvent) => void;
  className?: string;
}

export function EventEntities({ event, onReanalyze, className }: EventEntitiesProps) {
  const [entityModalOpen, setEntityModalOpen] = useState(false);
  const [entityCreateOpen, setEntityCreateOpen] = useState(false);
  const [isReclassifying, setIsReclassifying] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  const assignEventMutation = useAssignEventToEntity();
  const unlinkEventMutation = useUnlinkEvent();
  const queryClient = useQueryClient();

  // The open detail view holds a snapshot of the event, so the latest
  // mutation response wins until the server copy changes.
  const serverEntities = useMemo(() => eventEntitiesOf(event), [event]);
  const serverKey = `${event.id}:${serverEntities.map((entity) => entity.id).join(',')}`;
  const [override, setOverride] = useState<{ key: string; entities: IEventEntity[] } | null>(
    null
  );
  const entities =
    override && override.key === serverKey ? override.entities : serverEntities;
  const linkedIds = useMemo(() => entities.map((entity) => entity.id), [entities]);
  const atCapacity = entities.length >= MAX_ENTITIES_PER_EVENT;

  const applyEntities = useCallback(
    (next: IEventEntity[] | undefined, fallback: IEventEntity[]) => {
      const list = Array.isArray(next)
        ? next.map((entity) => ({ ...entity, id: String(entity.id) }))
        : fallback;
      setOverride({ key: serverKey, entities: list });
    },
    [serverKey]
  );

  const handleEntitySelect = useCallback(
    async (entityId: string, entityName: string | null) => {
      try {
        const result = await assignEventMutation.mutateAsync({
          eventId: event.id,
          entityId: String(entityId),
        });
        applyEntities(result.entities, entities);
        toast.success(result.message);
        setEntityModalOpen(false);
        if (result.action === 'none') return;

        // Story P16-4.3: re-classify so the description can use the name.
        setIsReclassifying(true);
        try {
          const updatedEvent = await apiClient.events.reanalyze(event.id, 'single_frame');
          toast.success('Event re-classified successfully', {
            description: entityName
              ? `Updated description with "${entityName}" context`
              : 'Updated description with entity context',
          });
          applyReanalyzedEvent(queryClient, updatedEvent);
          queryClient.invalidateQueries({ queryKey: ['events'] });
          queryClient.invalidateQueries({ queryKey: ['event', event.id] });
          onReanalyze?.(updatedEvent);
        } catch (reclassifyError) {
          const detail =
            reclassifyError instanceof Error ? reclassifyError.message.trim() : '';
          toast.error('Re-classification failed', {
            description: detail
              ? `Entity was assigned, but the description could not be updated. ${detail}`
              : 'Entity was assigned but description could not be updated',
          });
        } finally {
          setIsReclassifying(false);
        }
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Failed to assign event');
      }
    },
    [event.id, entities, assignEventMutation, applyEntities, queryClient, onReanalyze]
  );

  const handleRemove = useCallback(
    async (entity: IEventEntity) => {
      const label = getEntityDisplayName(entity);
      setRemovingId(entity.id);
      try {
        const result = await unlinkEventMutation.mutateAsync({
          entityId: String(entity.id),
          eventId: event.id,
        });
        applyEntities(
          result.entities,
          entities.filter((item) => item.id !== entity.id)
        );
        toast.success(`Removed ${label} from this event`);
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : `Failed to remove ${label}`
        );
      } finally {
        setRemovingId(null);
      }
    },
    [event.id, entities, unlinkEventMutation, applyEntities]
  );

  const handleCreateNewFromSelect = useCallback(() => {
    setEntityModalOpen(false);
    setEntityCreateOpen(true);
  }, []);

  const handleEntityCreated = useCallback(
    async (entityId: string, entityName: string | null) => {
      setEntityCreateOpen(false);
      await handleEntitySelect(entityId, entityName);
    },
    [handleEntitySelect]
  );

  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      <ReclassifyingIndicator isActive={isReclassifying} />
      <EventEntityChips
        entities={entities}
        onRemove={handleRemove}
        removingId={removingId}
        disabled={isReclassifying}
      />
      <Button
        variant="ghost"
        size="sm"
        className="h-7 px-2 text-xs"
        disabled={atCapacity || isReclassifying}
        title={
          atCapacity
            ? `An event can have at most ${MAX_ENTITIES_PER_EVENT} entities`
            : undefined
        }
        onClick={(e) => {
          e.stopPropagation();
          setEntityModalOpen(true);
        }}
      >
        <UserPlus className="h-3 w-3 mr-1" />
        Add to Entity
      </Button>

      <EntitySelectModal
        open={entityModalOpen}
        onOpenChange={setEntityModalOpen}
        onSelect={handleEntitySelect}
        onCreateNew={handleCreateNewFromSelect}
        title="Add to Entity"
        description={
          entities.length > 0
            ? 'Select another entity for this event. Entities already on it stay linked.'
            : 'Select an entity to associate this event with'
        }
        isLoading={assignEventMutation.isPending}
        excludeEntityIds={linkedIds}
      />

      <EntityCreateModal
        open={entityCreateOpen}
        onOpenChange={setEntityCreateOpen}
        onCreated={handleEntityCreated}
      />
    </div>
  );
}
