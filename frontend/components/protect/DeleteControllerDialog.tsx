/**
 * Delete Controller Confirmation Dialog
 * Story P2-1.5: Delete controller with confirmation
 *
 * Displays a destructive AlertDialog requiring user confirmation
 * before deleting a Protect controller. Shows controller name
 * and warns about disconnection.
 */

'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, AlertTriangle } from 'lucide-react';

import { apiClient, ApiError } from '@/lib/api-client';
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

interface DeleteControllerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  controllerId: string;
  controllerName: string;
  onDeleteSuccess?: () => void;
}

export function DeleteControllerDialog({
  open,
  onOpenChange,
  controllerId,
  controllerName,
  onDeleteSuccess,
}: DeleteControllerDialogProps) {
  const queryClient = useQueryClient();

  const deleteMutation = useMutation({
    mutationFn: async () => {
      return apiClient.protect.deleteController(controllerId);
    },
    onSuccess: () => {
      // Invalidate controller queries to refresh data
      queryClient.invalidateQueries({ queryKey: ['protect-controllers'] });
      queryClient.invalidateQueries({ queryKey: ['protectControllers'] });

      toast.success(`Controller "${controllerName}" has been removed`);
      onOpenChange(false);
      onDeleteSuccess?.();
    },
    onError: (error: Error) => {
      let errorMessage = 'Failed to delete controller';

      if (error instanceof ApiError) {
        errorMessage = error.message || errorMessage;
      }

      toast.error(errorMessage);
    },
  });

  const handleDelete = () => {
    deleteMutation.mutate();
  };

  const isDeleting = deleteMutation.isPending;

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-destructive" />
            Remove Controller
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-2">
              <p>
                Are you sure you want to remove <strong>{controllerName}</strong>?
              </p>
              <p>
                This will disconnect the WebSocket connection and disassociate any
                cameras linked to this controller. The cameras and their events will
                be preserved but no longer receive Protect updates.
              </p>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              handleDelete();
            }}
            disabled={isDeleting}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {isDeleting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            Remove Controller
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
