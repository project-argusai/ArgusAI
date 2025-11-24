/**
 * ConfirmDialog Component
 * Reusable confirmation modal for dangerous actions
 */

'use client';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { AlertTriangle } from 'lucide-react';
import { useState } from 'react';

export interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  requireCheckbox?: boolean;
  checkboxLabel?: string;
  onConfirm: () => void | Promise<void>;
  variant?: 'destructive' | 'default';
  isLoading?: boolean;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  requireCheckbox = false,
  checkboxLabel = 'I understand this cannot be undone',
  onConfirm,
  variant = 'default',
  isLoading = false,
}: ConfirmDialogProps) {
  const [checkboxChecked, setCheckboxChecked] = useState(false);

  const handleConfirm = async () => {
    await onConfirm();
    setCheckboxChecked(false); // Reset checkbox after confirm
  };

  const handleCancel = () => {
    setCheckboxChecked(false);
    onOpenChange(false);
  };

  const isConfirmDisabled = isLoading || (requireCheckbox && !checkboxChecked);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <div className="flex items-center gap-2">
            {variant === 'destructive' && (
              <AlertTriangle className="h-5 w-5 text-destructive" />
            )}
            <DialogTitle>{title}</DialogTitle>
          </div>
          <DialogDescription className="pt-2">{description}</DialogDescription>
        </DialogHeader>

        {requireCheckbox && (
          <div className="flex items-center space-x-2 py-4">
            <Checkbox
              id="confirm-checkbox"
              checked={checkboxChecked}
              onCheckedChange={(checked) => setCheckboxChecked(!!checked)}
              disabled={isLoading}
            />
            <Label
              htmlFor="confirm-checkbox"
              className="text-sm font-normal leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
            >
              {checkboxLabel}
            </Label>
          </div>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={handleCancel}
            disabled={isLoading}
            autoFocus
          >
            {cancelLabel}
          </Button>
          <Button
            variant={variant === 'destructive' ? 'destructive' : 'default'}
            onClick={handleConfirm}
            disabled={isConfirmDisabled}
          >
            {isLoading ? 'Processing...' : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
