/**
 * Cost Warning Modal Component
 * Story P8-2.3: Displays warning about cost implications when changing frame count
 */

'use client';

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
import { AlertTriangle } from 'lucide-react';

interface CostWarningModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  newValue: number;
  onConfirm: () => void;
  onCancel: () => void;
}

export function CostWarningModal({
  open,
  onOpenChange,
  newValue,
  onConfirm,
  onCancel,
}: CostWarningModalProps) {
  const handleConfirm = () => {
    onConfirm();
    onOpenChange(false);
  };

  const handleCancel = () => {
    onCancel();
    onOpenChange(false);
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-yellow-500" />
            More Frames = Higher Costs
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-4">
              <p>
                Increasing the number of analysis frames may improve description accuracy
                but will increase AI costs. Each frame is sent to the AI provider for analysis.
              </p>

              <div className="bg-muted p-3 rounded-md">
                <p className="font-medium mb-2">Estimated cost per event:</p>
                <ul className="space-y-1 text-sm">
                  <li className={newValue === 5 ? 'font-medium text-primary' : ''}>
                    5 frames: ~$0.001 per event
                  </li>
                  <li className={newValue === 10 ? 'font-medium text-primary' : ''}>
                    10 frames: ~$0.002 per event
                  </li>
                  <li className={newValue === 15 ? 'font-medium text-primary' : ''}>
                    15 frames: ~$0.003 per event
                  </li>
                  <li className={newValue === 20 ? 'font-medium text-primary' : ''}>
                    20 frames: ~$0.004 per event
                  </li>
                </ul>
              </div>

              <p className="text-sm text-muted-foreground">
                You are about to set the frame count to <span className="font-medium">{newValue} frames</span>.
              </p>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={handleCancel}>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={handleConfirm}>
            Confirm Change
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
