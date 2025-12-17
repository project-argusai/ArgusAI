'use client';

import { UseFormReturn } from 'react-hook-form';
import { useCamerasQuery } from '@/hooks/useCamerasQuery';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import type { RuleFormValues } from './RuleFormDialog';

interface CameraSelectorProps {
  form: UseFormReturn<RuleFormValues>;
}

export function CameraSelector({ form }: CameraSelectorProps) {
  // Use standardized camera query hook (Story P6-1.4)
  const { data: cameras, isLoading } = useCamerasQuery();

  const selectedCameras = form.watch('conditions.cameras') || [];

  const handleToggle = (cameraId: string) => {
    const current = form.getValues('conditions.cameras') || [];
    const updated = current.includes(cameraId)
      ? current.filter((id: string) => id !== cameraId)
      : [...current, cameraId];
    form.setValue('conditions.cameras', updated, { shouldValidate: true });
  };

  const handleSelectAll = () => {
    if (!cameras) return;
    const allIds = cameras.map((c) => c.id);
    const allSelected = allIds.every((id) => selectedCameras.includes(id));
    form.setValue('conditions.cameras', allSelected ? [] : allIds, { shouldValidate: true });
  };

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Label>Cameras</Label>
        <div className="flex gap-2">
          <Skeleton className="h-5 w-24" />
          <Skeleton className="h-5 w-24" />
        </div>
      </div>
    );
  }

  if (!cameras || cameras.length === 0) {
    return (
      <div className="space-y-2">
        <Label>Cameras</Label>
        <p className="text-sm text-muted-foreground">
          No cameras configured. Rule will apply to all cameras.
        </p>
      </div>
    );
  }

  const allSelected = cameras.length > 0 && cameras.every((c) => selectedCameras.includes(c.id));
  const someSelected = selectedCameras.length > 0 && !allSelected;

  return (
    <div className="space-y-2">
      <Label>Cameras</Label>
      <p className="text-sm text-muted-foreground mb-2">
        Select specific cameras or leave empty for all cameras
      </p>
      <div className="flex flex-wrap gap-3">
        <div className="flex items-center space-x-2">
          <Checkbox
            id="camera-all"
            checked={allSelected}
            ref={(el: HTMLButtonElement | null) => {
              if (el) {
                (el as HTMLButtonElement & { indeterminate: boolean }).indeterminate = someSelected;
              }
            }}
            onCheckedChange={handleSelectAll}
            aria-label="Select all cameras"
          />
          <Label htmlFor="camera-all" className="text-sm font-normal cursor-pointer">
            All Cameras
          </Label>
        </div>
        {cameras.map((camera) => (
          <div key={camera.id} className="flex items-center space-x-2">
            <Checkbox
              id={`camera-${camera.id}`}
              checked={selectedCameras.includes(camera.id)}
              onCheckedChange={() => handleToggle(camera.id)}
              aria-label={`Select ${camera.name}`}
            />
            <Label
              htmlFor={`camera-${camera.id}`}
              className="text-sm font-normal cursor-pointer"
            >
              {camera.name}
            </Label>
          </div>
        ))}
      </div>
    </div>
  );
}
