/**
 * EntityEditModal component - edit entity properties (Story P16-3.2)
 * AC1: Form with Name, Type, VIP toggle, Blocked toggle, Notes
 * AC2: Fields pre-filled with current entity values
 * AC3: Success toast, modal closes, view refreshes on save
 * AC4: Cancel/Escape closes without saving
 * AC5: Entity thumbnail at top
 * AC6: Form validation with inline errors
 * AC7: Save button disabled while saving
 */

'use client';

import { useCallback, useEffect } from 'react';
import { User, Car, HelpCircle, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { z } from 'zod';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
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
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { useUpdateEntity } from '@/hooks/useEntities';
import type { EntityType } from '@/types/entity';

// Form validation schema (Story P16-3.1 constraints)
const entityEditSchema = z.object({
  name: z.string().max(255, 'Name must be 255 characters or less').optional().nullable(),
  entity_type: z.enum(['person', 'vehicle', 'unknown']),
  is_vip: z.boolean(),
  is_blocked: z.boolean(),
  notes: z.string().max(2000, 'Notes must be 2000 characters or less').optional().nullable(),
});

type EntityEditFormValues = z.infer<typeof entityEditSchema>;

/**
 * Entity data required for editing
 */
export interface EntityEditData {
  id: string;
  entity_type: string;
  name: string | null;
  notes?: string | null;
  is_vip?: boolean;
  is_blocked?: boolean;
  thumbnail_path?: string | null;
}

interface EntityEditModalProps {
  /** Whether the modal is open */
  open: boolean;
  /** Callback when modal open state changes */
  onOpenChange: (open: boolean) => void;
  /** The entity to edit */
  entity: EntityEditData | null;
  /** Callback when entity is updated successfully */
  onUpdated?: () => void;
}

const ENTITY_TYPE_OPTIONS: Array<{
  value: EntityType;
  label: string;
  icon: React.ReactNode;
}> = [
  {
    value: 'person',
    label: 'Person',
    icon: <User className="h-4 w-4" />,
  },
  {
    value: 'vehicle',
    label: 'Vehicle',
    icon: <Car className="h-4 w-4" />,
  },
  {
    value: 'unknown',
    label: 'Unknown',
    icon: <HelpCircle className="h-4 w-4" />,
  },
];

/**
 * EntityEditModal - modal for editing entity properties
 */
export function EntityEditModal({
  open,
  onOpenChange,
  entity,
  onUpdated,
}: EntityEditModalProps) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? '';
  const updateEntityMutation = useUpdateEntity();

  const form = useForm<EntityEditFormValues>({
    resolver: zodResolver(entityEditSchema),
    defaultValues: {
      name: '',
      entity_type: 'unknown',
      is_vip: false,
      is_blocked: false,
      notes: '',
    },
  });

  // Reset form when entity changes or modal opens
  useEffect(() => {
    if (entity && open) {
      form.reset({
        name: entity.name ?? '',
        entity_type: (entity.entity_type as EntityType) || 'unknown',
        is_vip: entity.is_vip ?? false,
        is_blocked: entity.is_blocked ?? false,
        notes: entity.notes ?? '',
      });
    }
  }, [entity, open, form]);

  // Handle form submission
  const handleSubmit = useCallback(async (values: EntityEditFormValues) => {
    if (!entity) return;

    try {
      await updateEntityMutation.mutateAsync({
        entityId: entity.id,
        name: values.name || null,
        entity_type: values.entity_type,
        is_vip: values.is_vip,
        is_blocked: values.is_blocked,
        notes: values.notes || null,
      });
      toast.success('Entity updated');
      onOpenChange(false);
      onUpdated?.();
    } catch (error) {
      toast.error('Failed to update entity', {
        description: error instanceof Error ? error.message : 'Unknown error',
      });
    }
  }, [entity, updateEntityMutation, onOpenChange, onUpdated]);

  // Handle modal close
  const handleOpenChange = useCallback((newOpen: boolean) => {
    if (!newOpen) {
      form.reset();
    }
    onOpenChange(newOpen);
  }, [onOpenChange, form]);

  // Get thumbnail URL
  const thumbnailUrl = entity?.thumbnail_path
    ? `${apiUrl}${entity.thumbnail_path}`
    : null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Edit Entity</DialogTitle>
          <DialogDescription>
            Update the properties of this entity.
          </DialogDescription>
        </DialogHeader>

        {/* Entity Thumbnail (AC5) */}
        {thumbnailUrl && (
          <div className="flex justify-center mb-4">
            <img
              src={thumbnailUrl}
              alt={entity?.name || 'Entity thumbnail'}
              className="h-24 w-24 rounded-lg object-cover border"
            />
          </div>
        )}

        <Form {...form}>
          <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
            {/* Name */}
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="e.g., Mail Carrier, Neighbor"
                      {...field}
                      value={field.value ?? ''}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Entity Type */}
            <FormField
              control={form.control}
              name="entity_type"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Type</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select entity type" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {ENTITY_TYPE_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          <div className="flex items-center gap-2">
                            {option.icon}
                            <span>{option.label}</span>
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* VIP Toggle */}
            <FormField
              control={form.control}
              name="is_vip"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                  <div className="space-y-0.5">
                    <FormLabel>VIP</FormLabel>
                    <FormDescription>
                      Mark as a VIP for priority alerts
                    </FormDescription>
                  </div>
                  <FormControl>
                    <Switch
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                </FormItem>
              )}
            />

            {/* Blocked Toggle */}
            <FormField
              control={form.control}
              name="is_blocked"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                  <div className="space-y-0.5">
                    <FormLabel>Blocked</FormLabel>
                    <FormDescription>
                      Block this entity from alerts
                    </FormDescription>
                  </div>
                  <FormControl>
                    <Switch
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                </FormItem>
              )}
            />

            {/* Notes */}
            <FormField
              control={form.control}
              name="notes"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Notes</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Any additional notes about this entity..."
                      className="resize-none"
                      rows={3}
                      {...field}
                      value={field.value ?? ''}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => handleOpenChange(false)}
                disabled={updateEntityMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={updateEntityMutation.isPending}
              >
                {updateEntityMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Saving...
                  </>
                ) : (
                  'Save'
                )}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
