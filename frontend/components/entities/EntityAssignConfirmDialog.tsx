/**
 * EntityAssignConfirmDialog component - confirmation dialog for entity assignment (Story P16-4.1, P16-4.2)
 * AC-4.1.1: Confirmation dialog appears before assignment
 * AC-4.1.2: Shows entity name in message
 * AC-4.1.3: Shows re-classification info
 * AC-4.1.4: Shows estimated API cost
 * AC-4.1.5: Confirm triggers assignment
 * AC-4.1.6: Cancel returns to entity selection
 * AC-4.2.1: "Don't show again" checkbox
 * AC-4.2.2: Save preference to localStorage on confirm
 */

'use client';

import { useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
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

/** localStorage key for "Don't show again" preference (Story P16-4.2) */
export const SKIP_ENTITY_ASSIGN_WARNING_KEY = 'argusai_skip_entity_assign_warning';

interface EntityAssignConfirmDialogProps {
  /** Whether the dialog is open */
  open: boolean;
  /** Callback when dialog open state changes */
  onOpenChange: (open: boolean) => void;
  /** Entity name to display in the confirmation message */
  entityName: string;
  /** Callback when user confirms the assignment */
  onConfirm: () => void;
  /** Callback when user cancels the assignment */
  onCancel: () => void;
  /** Whether the confirmation action is in progress */
  isLoading?: boolean;
  /** Estimated cost for re-analysis (default: ~$0.002) */
  estimatedCost?: string;
}

/**
 * EntityAssignConfirmDialog - warns user about AI re-classification before entity assignment
 */
export function EntityAssignConfirmDialog({
  open,
  onOpenChange,
  entityName,
  onConfirm,
  onCancel,
  isLoading = false,
  estimatedCost = '~$0.002',
}: EntityAssignConfirmDialogProps) {
  // Story P16-4.2: State for "Don't show again" checkbox
  const [dontShowAgain, setDontShowAgain] = useState(false);

  const handleCancel = () => {
    setDontShowAgain(false); // Reset checkbox on cancel
    onCancel();
    onOpenChange(false);
  };

  const handleConfirm = () => {
    // Story P16-4.2: Save preference to localStorage if checkbox is checked
    if (dontShowAgain) {
      try {
        localStorage.setItem(SKIP_ENTITY_ASSIGN_WARNING_KEY, 'true');
      } catch {
        // localStorage might not be available (e.g., in incognito mode)
      }
    }
    onConfirm();
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-500" />
            <AlertDialogTitle>Confirm Entity Assignment</AlertDialogTitle>
          </div>
          <AlertDialogDescription asChild>
            <div className="space-y-3 pt-2">
              <p>
                Assigning this event to <strong>{entityName}</strong> will trigger AI re-classification.
              </p>
              <p>
                This will update the event description based on the entity context.
              </p>
              <p className="text-xs text-muted-foreground">
                Estimated API cost: {estimatedCost} for re-analysis
              </p>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>

        {/* Story P16-4.2: "Don't show again" checkbox */}
        <div className="flex items-center space-x-2">
          <Checkbox
            id="dont-show-again"
            checked={dontShowAgain}
            onCheckedChange={(checked) => setDontShowAgain(checked === true)}
            aria-label="Don't show this warning again"
          />
          <Label
            htmlFor="dont-show-again"
            className="text-sm text-muted-foreground cursor-pointer"
          >
            Don&apos;t show this warning again
          </Label>
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel onClick={handleCancel} disabled={isLoading}>
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction onClick={handleConfirm} disabled={isLoading}>
            {isLoading ? 'Assigning...' : 'Confirm'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
