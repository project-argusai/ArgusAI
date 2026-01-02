/**
 * EntitySelectModal component - select an entity to assign an event to (Story P9-4.4)
 * AC-4.4.3: Searchable entity list modal
 * AC-4.4.4: Filter entities by search query
 * Story P10-4.1: Added "Create New Entity" button (AC-4.1.7)
 */

'use client';

import { useState, useMemo, useCallback, useEffect } from 'react';
import { Search, User, Car, HelpCircle, Check, Plus } from 'lucide-react';
import { toast } from 'sonner';
import { EntityAssignConfirmDialog, SKIP_ENTITY_ASSIGN_WARNING_KEY } from './EntityAssignConfirmDialog';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { useEntities } from '@/hooks/useEntities';
import { cn } from '@/lib/utils';
import type { EntityType } from '@/types/entity';

interface EntitySelectModalProps {
  /** Whether the modal is open */
  open: boolean;
  /** Callback when modal open state changes */
  onOpenChange: (open: boolean) => void;
  /** Callback when an entity is selected and confirmed */
  onSelect: (entityId: string, entityName: string | null) => void;
  /** Story P10-4.1: Callback when "Create New Entity" is clicked. If not provided, shows "Coming soon" toast */
  onCreateNew?: () => void;
  /** Title to display in the modal */
  title?: string;
  /** Description to display in the modal */
  description?: string;
  /** Whether the selection is in progress */
  isLoading?: boolean;
  /** Story P16-4.1: Whether to show confirmation dialog before assignment (default: true) */
  showConfirmDialog?: boolean;
}

interface EntityListItem {
  id: string;
  entity_type: EntityType;
  name: string | null;
  occurrence_count: number;
  first_seen_at: string;
  last_seen_at: string;
}

const ENTITY_ICONS: Record<EntityType, React.ReactNode> = {
  person: <User className="h-4 w-4" />,
  vehicle: <Car className="h-4 w-4" />,
  unknown: <HelpCircle className="h-4 w-4" />,
};

/**
 * EntitySelectModal - modal for selecting an entity to assign an event to
 */
export function EntitySelectModal({
  open,
  onOpenChange,
  onSelect,
  onCreateNew,
  title = 'Select Entity',
  description = 'Choose an entity to assign this event to',
  isLoading = false,
  showConfirmDialog = true,
}: EntitySelectModalProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  // Story P16-4.1: State for confirmation dialog
  const [showConfirmation, setShowConfirmation] = useState(false);
  // Story P16-4.2: State to track if user has opted out of confirmation dialog
  const [skipWarning, setSkipWarning] = useState(false);

  // Story P16-4.2: Check localStorage for "Don't show again" preference on mount
  useEffect(() => {
    try {
      const savedPreference = localStorage.getItem(SKIP_ENTITY_ASSIGN_WARNING_KEY);
      setSkipWarning(savedPreference === 'true');
    } catch {
      // localStorage might not be available
    }
  }, []);

  // Fetch entities with search filter (debounced via react-query)
  const { data: entitiesData, isLoading: isLoadingEntities } = useEntities({
    limit: 100,
    search: searchQuery || undefined,
  });

  const entities = useMemo(() => {
    return (entitiesData?.entities ?? []) as EntityListItem[];
  }, [entitiesData]);

  // Get selected entity details
  const selectedEntity = useMemo(() => {
    if (!selectedEntityId) return null;
    return entities.find((e) => e.id === selectedEntityId) || null;
  }, [selectedEntityId, entities]);

  // Handle entity selection
  const handleEntityClick = useCallback((e: React.MouseEvent, entityId: string) => {
    e.stopPropagation();
    setSelectedEntityId((prev) => (prev === entityId ? null : entityId));
  }, []);

  // Handle confirm button - Story P16-4.1/P16-4.2: Show confirmation dialog if enabled and not skipped
  const handleConfirm = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (selectedEntity) {
      // Story P16-4.2: Skip dialog if user has opted out via "Don't show again"
      if (showConfirmDialog && !skipWarning) {
        // Show confirmation dialog before assignment
        setShowConfirmation(true);
      } else {
        // Skip confirmation and assign directly
        onSelect(selectedEntity.id, selectedEntity.name);
      }
    }
  }, [selectedEntity, onSelect, showConfirmDialog, skipWarning]);

  // Story P16-4.1: Handle confirmation dialog confirm
  const handleConfirmDialogConfirm = useCallback(() => {
    if (selectedEntity) {
      onSelect(selectedEntity.id, selectedEntity.name);
      setShowConfirmation(false);
    }
  }, [selectedEntity, onSelect]);

  // Story P16-4.1: Handle confirmation dialog cancel
  const handleConfirmDialogCancel = useCallback(() => {
    setShowConfirmation(false);
  }, []);

  // Reset state when modal closes
  const handleOpenChange = useCallback((newOpen: boolean) => {
    if (!newOpen) {
      setSearchQuery('');
      setSelectedEntityId(null);
      setShowConfirmation(false);
    }
    onOpenChange(newOpen);
  }, [onOpenChange]);

  // Format entity display name
  const getEntityDisplayName = (entity: EntityListItem) => {
    if (entity.name) return entity.name;
    return `${entity.entity_type.charAt(0).toUpperCase() + entity.entity_type.slice(1)} #${entity.id.slice(0, 8)}`;
  };

  // Story P10-4.1: Handle "Create New Entity" button click (AC-4.1.7)
  const handleCreateNew = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (onCreateNew) {
      onCreateNew();
    } else {
      // Stub: show "Coming soon" toast when no callback is provided
      toast.info('Create Entity coming soon', {
        description: 'This feature will be available in a future update.',
      });
    }
  }, [onCreateNew]);

  return (
    <>
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md" onClick={(e) => e.stopPropagation()}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        {/* Search input */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search entities..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
            autoFocus
          />
        </div>

        {/* Entity list */}
        <ScrollArea className="h-[300px] rounded-md border">
          <div className="p-2 space-y-1">
            {isLoadingEntities ? (
              // Loading skeleton
              Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="flex items-center gap-3 p-2">
                  <Skeleton className="h-8 w-8 rounded-full" />
                  <div className="flex-1 space-y-1">
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-3 w-1/2" />
                  </div>
                </div>
              ))
            ) : entities.length === 0 ? (
              // Empty state
              <div className="flex flex-col items-center justify-center py-8 text-center">
                <HelpCircle className="h-8 w-8 text-muted-foreground mb-2" />
                <p className="text-sm text-muted-foreground">
                  {searchQuery
                    ? `No entities found matching "${searchQuery}"`
                    : 'No entities available'}
                </p>
              </div>
            ) : (
              // Entity list items
              entities.map((entity) => {
                const isSelected = entity.id === selectedEntityId;
                return (
                  <button
                    key={entity.id}
                    type="button"
                    onClick={(e) => handleEntityClick(e, entity.id)}
                    className={cn(
                      'w-full flex items-center gap-3 p-2 rounded-md text-left transition-colors',
                      'hover:bg-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                      isSelected && 'bg-primary/10 border border-primary'
                    )}
                  >
                    {/* Entity type icon */}
                    <div
                      className={cn(
                        'flex items-center justify-center h-8 w-8 rounded-full',
                        entity.entity_type === 'person' && 'bg-blue-100 text-blue-600',
                        entity.entity_type === 'vehicle' && 'bg-green-100 text-green-600',
                        entity.entity_type === 'unknown' && 'bg-gray-100 text-gray-600'
                      )}
                    >
                      {ENTITY_ICONS[entity.entity_type]}
                    </div>

                    {/* Entity info */}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">
                        {getEntityDisplayName(entity)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {entity.entity_type} · {entity.occurrence_count} occurrence
                        {entity.occurrence_count !== 1 ? 's' : ''}
                      </p>
                    </div>

                    {/* Selection indicator */}
                    {isSelected && (
                      <Check className="h-4 w-4 text-primary flex-shrink-0" />
                    )}
                  </button>
                );
              })
            )}
          </div>
        </ScrollArea>

        {/* Story P10-4.1: Create New Entity button (AC-4.1.7) */}
        <Button
          variant="ghost"
          className="w-full justify-start text-muted-foreground hover:text-foreground"
          onClick={handleCreateNew}
          aria-label="Create new entity"
        >
          <Plus className="h-4 w-4 mr-2" />
          Create New Entity
        </Button>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={(e) => {
              e.stopPropagation();
              handleOpenChange(false);
            }}
            disabled={isLoading}
          >
            Cancel
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={!selectedEntityId || isLoading}
          >
            {isLoading ? 'Assigning...' : 'Confirm'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    {/* Story P16-4.1: Confirmation dialog for entity assignment */}
    {selectedEntity && (
      <EntityAssignConfirmDialog
        open={showConfirmation}
        onOpenChange={setShowConfirmation}
        entityName={getEntityDisplayName(selectedEntity)}
        onConfirm={handleConfirmDialogConfirm}
        onCancel={handleConfirmDialogCancel}
        isLoading={isLoading}
      />
    )}
    </>
  );
}
