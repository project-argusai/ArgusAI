/**
 * DeleteEntityDialog component - confirmation dialog for entity deletion (Story P4-3.6)
 * AC9: User can delete an entity with confirmation dialog
 * AC10: Delete confirmation shows warning about unlinking events
 * AC11: API error handling with user-friendly error messages
 */

'use client';

import { AlertTriangle, Loader2 } from 'lucide-react';
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
import { useDeleteEntity, isApiError } from '@/hooks/useEntities';
import { toast } from 'sonner';
import type { IEntity } from '@/types/entity';

interface DeleteEntityDialogProps {
  /** Entity to delete */
  entity: IEntity | null;
  /** Whether the dialog is open */
  open: boolean;
  /** Callback when dialog is closed/cancelled */
  onClose: () => void;
  /** Callback after successful deletion */
  onDeleted?: () => void;
}

/**
 * Confirmation dialog for deleting an entity
 */
export function DeleteEntityDialog({
  entity,
  open,
  onClose,
  onDeleted,
}: DeleteEntityDialogProps) {
  const deleteMutation = useDeleteEntity();

  const handleDelete = async () => {
    if (!entity) return;

    try {
      await deleteMutation.mutateAsync(entity.id);
      toast.success(
        entity.name
          ? `Deleted "${entity.name}"`
          : 'Entity deleted'
      );
      onDeleted?.();
      onClose();
    } catch (error) {
      if (isApiError(error)) {
        if (error.statusCode === 404) {
          toast.error('Entity not found - it may have already been deleted');
          onClose();
        } else {
          toast.error(`Failed to delete entity: ${error.message}`);
        }
      } else {
        toast.error('Failed to delete entity');
      }
    }
  };

  const displayName = entity?.name || `Unknown ${entity?.entity_type || 'entity'}`;

  return (
    <AlertDialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-destructive" />
            Delete Entity
          </AlertDialogTitle>
          <AlertDialogDescription className="space-y-3">
            <p>
              Are you sure you want to delete <strong>{displayName}</strong>?
            </p>
            <div className="bg-yellow-50 dark:bg-yellow-950/50 border border-yellow-200 dark:border-yellow-900 rounded-md p-3 text-sm text-yellow-800 dark:text-yellow-200">
              <strong>Note:</strong> This will unlink this entity from all
              associated events. The events themselves will not be deleted,
              only the connection to this entity.
            </div>
            {entity && (
              <p className="text-sm">
                This entity has been seen {entity.occurrence_count} time
                {entity.occurrence_count !== 1 ? 's' : ''}.
              </p>
            )}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={deleteMutation.isPending}>
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {deleteMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Deleting...
              </>
            ) : (
              'Delete Entity'
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
