/**
 * EntityPlateSection - enrol or remove a vehicle's license plate.
 *
 * Privacy rules:
 * - The plate is typed into an uncontrolled password-style input, read once on
 *   submit and cleared at once. It is never put in React state, storage,
 *   logs, toasts or URLs.
 * - Only "Plate on file" is shown, never the plate text or its hash.
 * - Hidden entirely unless plate recognition is enabled.
 */

'use client';

import { useRef } from 'react';
import { toast } from 'sonner';
import { Loader2, ScanLine, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ApiError } from '@/lib/api-client';
import {
  useAddPlate,
  useEntityPlates,
  usePlateStatus,
  useRemovePlate,
} from '@/hooks/useEntityPlates';

interface EntityPlateSectionProps {
  entityId: string;
  entityType: string;
}

export function EntityPlateSection({ entityId, entityType }: EntityPlateSectionProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const isVehicle = entityType === 'vehicle';
  const { data: status } = usePlateStatus(isVehicle);
  const visible = isVehicle && !!status?.enabled;
  const { data: saved } = useEntityPlates(entityId, visible);
  const addPlate = useAddPlate(entityId);
  const removePlate = useRemovePlate(entityId);

  if (!visible) return null;

  const records = saved?.plates ?? [];
  const onFile = records.length > 0;

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    const input = inputRef.current;
    if (!input) return;
    const value = input.value.trim();
    // Clear straight away; the value now lives only in this local variable.
    input.value = '';
    if (!value) return;
    try {
      await addPlate.mutateAsync(value);
      toast.success('Plate saved');
    } catch (error) {
      // Only show a message the server wrote about the problem; never echo input.
      const message =
        error instanceof ApiError && error.statusCode >= 400 && error.statusCode < 500
          ? error.message
          : 'Please try again';
      toast.error('Could not save plate', { description: message });
    }
  };

  const handleRemove = async () => {
    try {
      for (const record of records) {
        await removePlate.mutateAsync(record.id);
      }
      toast.success('Plate removed');
    } catch {
      toast.error('Could not remove plate');
    }
  };

  return (
    <div className="space-y-2 rounded-lg border p-3" data-testid="entity-plate-section">
      <div className="flex items-center justify-between gap-2">
        <div className="space-y-0.5">
          <Label htmlFor="entity-plate-input" className="flex items-center gap-2">
            <ScanLine className="h-4 w-4" />
            License plate
          </Label>
          <p className="text-sm text-muted-foreground">
            Helps recognise this vehicle. Saved as a one-way hash; the plate itself is never stored.
          </p>
        </div>
        {onFile && (
          <span className="text-sm font-medium" data-testid="plate-on-file">
            Plate on file
          </span>
        )}
      </div>

      <form onSubmit={handleAdd} className="flex items-center gap-2">
        <Input
          id="entity-plate-input"
          ref={inputRef}
          type="password"
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={20}
          data-1p-ignore
          placeholder={onFile ? 'Replace or add another plate' : 'Enter plate'}
          disabled={addPlate.isPending}
        />
        <Button type="submit" size="sm" disabled={addPlate.isPending}>
          {addPlate.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save plate'}
        </Button>
      </form>

      {onFile && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleRemove}
          disabled={removePlate.isPending}
        >
          <Trash2 className="mr-2 h-4 w-4" />
          Remove plate
        </Button>
      )}
    </div>
  );
}
