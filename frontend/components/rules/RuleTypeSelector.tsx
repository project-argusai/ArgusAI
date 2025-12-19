'use client';

import { UseFormReturn } from 'react-hook-form';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { RULE_TYPES } from '@/types/alert-rule';
import type { RuleFormValues } from './RuleFormDialog';

interface RuleTypeSelectorProps {
  form: UseFormReturn<RuleFormValues>;
}

/**
 * Rule type selector for alert rules (Story P7-2.2).
 *
 * Allows selection between:
 * - "Any Detection" (default): matches any detection type
 * - "Package Delivery": matches package deliveries with carrier identification
 */
export function RuleTypeSelector({ form }: RuleTypeSelectorProps) {
  const ruleType = form.watch('conditions.rule_type') || 'any';

  const handleChange = (value: string) => {
    form.setValue('conditions.rule_type', value, { shouldValidate: true });

    // Clear object_types when switching to package_delivery (handled automatically)
    if (value === 'package_delivery') {
      form.setValue('conditions.object_types', undefined);
    }
    // Clear carriers when switching away from package_delivery
    if (value === 'any') {
      form.setValue('conditions.carriers', undefined);
    }
  };

  return (
    <div className="space-y-3">
      <Label>Rule Type</Label>
      <RadioGroup
        value={ruleType}
        onValueChange={handleChange}
        className="flex flex-col gap-3"
      >
        {RULE_TYPES.map((type) => (
          <div key={type.value} className="flex items-start space-x-3">
            <RadioGroupItem
              value={type.value}
              id={`rule-type-${type.value}`}
              className="mt-0.5"
            />
            <div className="flex flex-col">
              <Label
                htmlFor={`rule-type-${type.value}`}
                className="text-sm font-medium cursor-pointer"
              >
                {type.label}
              </Label>
              <p className="text-xs text-muted-foreground">
                {type.description}
              </p>
            </div>
          </div>
        ))}
      </RadioGroup>
    </div>
  );
}
