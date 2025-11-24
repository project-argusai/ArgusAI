'use client';

import { UseFormReturn } from 'react-hook-form';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { OBJECT_TYPES } from '@/types/alert-rule';
import type { RuleFormValues } from './RuleFormDialog';

interface ObjectTypeSelectorProps {
  form: UseFormReturn<RuleFormValues>;
}

export function ObjectTypeSelector({ form }: ObjectTypeSelectorProps) {
  const selectedTypes = form.watch('conditions.object_types') || [];

  const handleToggle = (type: string) => {
    const current = form.getValues('conditions.object_types') || [];
    const updated = current.includes(type)
      ? current.filter((t: string) => t !== type)
      : [...current, type];
    form.setValue('conditions.object_types', updated, { shouldValidate: true });
  };

  return (
    <div className="space-y-2">
      <Label>Object Types</Label>
      <p className="text-sm text-muted-foreground mb-2">
        Select which object types should trigger this rule
      </p>
      <div className="flex flex-wrap gap-3">
        {OBJECT_TYPES.map((type) => (
          <div key={type} className="flex items-center space-x-2">
            <Checkbox
              id={`object-type-${type}`}
              checked={selectedTypes.includes(type)}
              onCheckedChange={() => handleToggle(type)}
              aria-label={`Select ${type}`}
            />
            <Label
              htmlFor={`object-type-${type}`}
              className="text-sm font-normal cursor-pointer capitalize"
            >
              {type}
            </Label>
          </div>
        ))}
      </div>
    </div>
  );
}
