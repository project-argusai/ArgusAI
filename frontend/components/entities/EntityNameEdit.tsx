/**
 * EntityNameEdit component - inline editing for entity names (Story P4-3.6)
 * AC8: User can assign/update entity name via inline edit
 * AC11: API error handling with user-friendly error messages
 */

'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { Pencil, Check, X, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useUpdateEntity, isApiError } from '@/hooks/useEntities';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface EntityNameEditProps {
  entityId: string;
  currentName: string | null;
}

/**
 * Inline entity name editor with save/cancel
 */
export function EntityNameEdit({ entityId, currentName }: EntityNameEditProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(currentName || '');
  const inputRef = useRef<HTMLInputElement>(null);

  const updateMutation = useUpdateEntity();

  // Focus input when entering edit mode
  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleStartEdit = useCallback(() => {
    setEditValue(currentName || '');
    setIsEditing(true);
  }, [currentName]);

  const handleCancel = useCallback(() => {
    setEditValue(currentName || '');
    setIsEditing(false);
  }, [currentName]);

  const handleSave = useCallback(async () => {
    const newName = editValue.trim() || null;

    // Don't save if unchanged
    if (newName === currentName) {
      setIsEditing(false);
      return;
    }

    try {
      await updateMutation.mutateAsync({
        entityId,
        name: newName,
      });
      toast.success(newName ? `Named entity "${newName}"` : 'Name removed');
      setIsEditing(false);
    } catch (error) {
      if (isApiError(error)) {
        toast.error(`Failed to update name: ${error.message}`);
      } else {
        toast.error('Failed to update entity name');
      }
      // Keep editing mode open on error
    }
  }, [editValue, currentName, entityId, updateMutation]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSave();
    } else if (e.key === 'Escape') {
      handleCancel();
    }
  }, [handleSave, handleCancel]);

  if (isEditing) {
    return (
      <div className="flex items-center gap-2">
        <Input
          ref={inputRef}
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Enter a name..."
          className="h-8 text-sm"
          disabled={updateMutation.isPending}
          maxLength={255}
        />
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={handleSave}
          disabled={updateMutation.isPending}
        >
          {updateMutation.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Check className="h-4 w-4 text-green-600" />
          )}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={handleCancel}
          disabled={updateMutation.isPending}
        >
          <X className="h-4 w-4 text-red-600" />
        </Button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 group">
      <span
        className={cn(
          'text-lg font-semibold',
          !currentName && 'text-muted-foreground italic'
        )}
      >
        {currentName || 'Unnamed'}
      </span>
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={handleStartEdit}
        title="Edit name"
      >
        <Pencil className="h-3 w-3" />
      </Button>
    </div>
  );
}
