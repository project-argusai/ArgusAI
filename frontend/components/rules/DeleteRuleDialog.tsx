'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { apiClient, ApiError } from '@/lib/api-client';
import type { IAlertRule } from '@/types/alert-rule';
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

interface DeleteRuleDialogProps {
  rule: IAlertRule | null;
  onClose: () => void;
}

export function DeleteRuleDialog({ rule, onClose }: DeleteRuleDialogProps) {
  const queryClient = useQueryClient();

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await apiClient.alertRules.delete(id);
      return id;
    },
    onMutate: async (id) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['alertRules'] });

      // Snapshot previous value
      const previousRules = queryClient.getQueryData(['alertRules']);

      // Optimistically remove
      queryClient.setQueryData(['alertRules'], (old: { data: IAlertRule[]; total_count: number } | undefined) => {
        if (!old) return old;
        return {
          data: old.data.filter((r) => r.id !== id),
          total_count: old.total_count - 1,
        };
      });

      return { previousRules };
    },
    onError: (err, _id, context) => {
      // Rollback on error
      if (context?.previousRules) {
        queryClient.setQueryData(['alertRules'], context.previousRules);
      }
      const message = err instanceof ApiError ? err.message : 'Failed to delete rule';
      toast.error(message);
    },
    onSuccess: () => {
      toast.success(`Rule "${rule?.name}" deleted`);
      onClose();
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['alertRules'] });
    },
  });

  const handleDelete = () => {
    if (rule) {
      deleteMutation.mutate(rule.id);
    }
  };

  return (
    <AlertDialog open={!!rule} onOpenChange={(open) => !open && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete &quot;{rule?.name}&quot;?</AlertDialogTitle>
          <AlertDialogDescription>
            This action cannot be undone. Alerts will no longer trigger for this rule.
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
            {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
