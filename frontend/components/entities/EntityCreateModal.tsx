/**
 * EntityCreateModal component - create a new entity manually (Story P10-4.2)
 * AC-4.2.2: Form with type, name, description fields
 * AC-4.2.3: Vehicle fields appear when type is "vehicle"
 * AC-4.2.7: Optional reference image upload
 * AC-4.2.8: Validation errors displayed
 */

'use client';

import { useState, useCallback, useRef } from 'react';
import { User, Car, HelpCircle, Upload, X, Loader2 } from 'lucide-react';
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
import { Label } from '@/components/ui/label';
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
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { useCreateEntity, type CreateEntityRequest } from '@/hooks/useEntities';
import type { EntityType } from '@/types/entity';

// Form validation schema
const entityFormSchema = z.object({
  entity_type: z.enum(['person', 'vehicle', 'unknown']),
  name: z.string().max(255).optional().nullable(),
  notes: z.string().optional().nullable(),
  vehicle_color: z.string().max(50).optional().nullable(),
  vehicle_make: z.string().max(50).optional().nullable(),
  vehicle_model: z.string().max(50).optional().nullable(),
}).refine((data) => {
  // Vehicle entities require at least color+make or make+model
  if (data.entity_type === 'vehicle') {
    const hasColorMake = data.vehicle_color && data.vehicle_make;
    const hasMakeModel = data.vehicle_make && data.vehicle_model;
    return hasColorMake || hasMakeModel;
  }
  return true;
}, {
  message: 'Vehicle entities require at least color + make OR make + model',
  path: ['vehicle_make'],
});

type EntityFormValues = z.infer<typeof entityFormSchema>;

interface EntityCreateModalProps {
  /** Whether the modal is open */
  open: boolean;
  /** Callback when modal open state changes */
  onOpenChange: (open: boolean) => void;
  /** Callback when entity is created successfully */
  onCreated?: (entityId: string, entityName: string | null) => void;
}

const ENTITY_TYPE_OPTIONS: Array<{
  value: EntityType;
  label: string;
  icon: React.ReactNode;
  description: string;
}> = [
  {
    value: 'person',
    label: 'Person',
    icon: <User className="h-4 w-4" />,
    description: 'A person or individual',
  },
  {
    value: 'vehicle',
    label: 'Vehicle',
    icon: <Car className="h-4 w-4" />,
    description: 'A car, truck, or other vehicle',
  },
  {
    value: 'unknown',
    label: 'Other',
    icon: <HelpCircle className="h-4 w-4" />,
    description: 'Other type of entity',
  },
];

// Common vehicle colors for suggestions
const VEHICLE_COLORS = [
  'white', 'black', 'silver', 'gray', 'red', 'blue', 'green',
  'brown', 'beige', 'gold', 'orange', 'yellow', 'purple',
];

/**
 * EntityCreateModal - modal for creating a new entity manually
 */
export function EntityCreateModal({
  open,
  onOpenChange,
  onCreated,
}: EntityCreateModalProps) {
  const [referenceImage, setReferenceImage] = useState<string | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const createEntityMutation = useCreateEntity();

  const form = useForm<EntityFormValues>({
    resolver: zodResolver(entityFormSchema),
    defaultValues: {
      entity_type: 'person',
      name: '',
      notes: '',
      vehicle_color: '',
      vehicle_make: '',
      vehicle_model: '',
    },
  });

  const selectedType = form.watch('entity_type');

  // Handle image selection
  const handleImageSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Check file size (2MB limit)
    if (file.size > 2 * 1024 * 1024) {
      toast.error('Image too large', {
        description: 'Please select an image under 2MB',
      });
      return;
    }

    // Check file type
    if (!file.type.match(/^image\/(jpeg|png|webp)$/)) {
      toast.error('Invalid file type', {
        description: 'Please select a JPEG, PNG, or WebP image',
      });
      return;
    }

    // Read as base64
    const reader = new FileReader();
    reader.onload = (event) => {
      const base64 = event.target?.result as string;
      setReferenceImage(base64);
      setImagePreview(base64);
    };
    reader.readAsDataURL(file);
  }, []);

  // Clear image
  const handleClearImage = useCallback(() => {
    setReferenceImage(null);
    setImagePreview(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, []);

  // Handle form submission
  const handleSubmit = useCallback(async (values: EntityFormValues) => {
    const request: CreateEntityRequest = {
      entity_type: values.entity_type,
      name: values.name || null,
      notes: values.notes || null,
      vehicle_color: values.entity_type === 'vehicle' ? (values.vehicle_color || null) : null,
      vehicle_make: values.entity_type === 'vehicle' ? (values.vehicle_make || null) : null,
      vehicle_model: values.entity_type === 'vehicle' ? (values.vehicle_model || null) : null,
      reference_image: referenceImage || null,
    };

    try {
      const created = await createEntityMutation.mutateAsync(request);
      toast.success('Entity created', {
        description: created.name || created.vehicle_signature || `${created.entity_type} entity`,
      });
      onOpenChange(false);
      onCreated?.(created.id, created.name);
      // Reset form
      form.reset();
      handleClearImage();
    } catch (error) {
      toast.error('Failed to create entity', {
        description: error instanceof Error ? error.message : 'Unknown error',
      });
    }
  }, [referenceImage, createEntityMutation, onOpenChange, onCreated, form, handleClearImage]);

  // Reset form when modal closes
  const handleOpenChange = useCallback((newOpen: boolean) => {
    if (!newOpen) {
      form.reset();
      handleClearImage();
    }
    onOpenChange(newOpen);
  }, [onOpenChange, form, handleClearImage]);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Create New Entity</DialogTitle>
          <DialogDescription>
            Pre-register a person, vehicle, or other entity before they appear on camera.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
            {/* Entity Type */}
            <FormField
              control={form.control}
              name="entity_type"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Type</FormLabel>
                  <Select onValueChange={field.onChange} defaultValue={field.value}>
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

            {/* Name */}
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name (optional)</FormLabel>
                  <FormControl>
                    <Input
                      placeholder={selectedType === 'vehicle' ? "e.g., Dad's Truck" : "e.g., Mail Carrier"}
                      {...field}
                      value={field.value ?? ''}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Vehicle-specific fields */}
            {selectedType === 'vehicle' && (
              <div className="space-y-4 rounded-lg border p-4 bg-muted/30">
                <p className="text-sm font-medium text-muted-foreground">Vehicle Details</p>

                {/* Color */}
                <FormField
                  control={form.control}
                  name="vehicle_color"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Color</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value ?? ''}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select color" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {VEHICLE_COLORS.map((color) => (
                            <SelectItem key={color} value={color}>
                              <div className="flex items-center gap-2">
                                <div
                                  className="h-3 w-3 rounded-full border"
                                  style={{
                                    backgroundColor: color === 'white' ? '#f5f5f5' :
                                      color === 'silver' ? '#c0c0c0' :
                                      color === 'gray' ? '#808080' :
                                      color === 'beige' ? '#f5f5dc' :
                                      color === 'gold' ? '#ffd700' :
                                      color
                                  }}
                                />
                                <span className="capitalize">{color}</span>
                              </div>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* Make */}
                <FormField
                  control={form.control}
                  name="vehicle_make"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Make</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="e.g., Toyota, Ford, Honda"
                          {...field}
                          value={field.value ?? ''}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* Model */}
                <FormField
                  control={form.control}
                  name="vehicle_model"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Model</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="e.g., Camry, F-150, Civic"
                          {...field}
                          value={field.value ?? ''}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            )}

            {/* Notes */}
            <FormField
              control={form.control}
              name="notes"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Notes (optional)</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Any additional notes about this entity..."
                      className="resize-none"
                      rows={2}
                      {...field}
                      value={field.value ?? ''}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Reference Image */}
            <div className="space-y-2">
              <Label>Reference Image (optional)</Label>
              <div className="flex items-center gap-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={handleImageSelect}
                  className="hidden"
                />
                {imagePreview ? (
                  <div className="relative">
                    <img
                      src={imagePreview}
                      alt="Reference"
                      className="h-20 w-20 rounded-lg object-cover border"
                    />
                    <Button
                      type="button"
                      variant="destructive"
                      size="icon"
                      className="absolute -top-2 -right-2 h-6 w-6"
                      onClick={handleClearImage}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                ) : (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => fileInputRef.current?.click()}
                    className="h-20 w-20 flex-col gap-1"
                  >
                    <Upload className="h-5 w-5" />
                    <span className="text-xs">Upload</span>
                  </Button>
                )}
                <p className="text-xs text-muted-foreground">
                  Max 2MB, JPEG/PNG/WebP
                </p>
              </div>
            </div>

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => handleOpenChange(false)}
                disabled={createEntityMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={createEntityMutation.isPending}
              >
                {createEntityMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Creating...
                  </>
                ) : (
                  'Create Entity'
                )}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
