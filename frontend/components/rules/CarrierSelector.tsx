'use client';

import { UseFormReturn } from 'react-hook-form';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { CARRIERS } from '@/types/alert-rule';
import type { RuleFormValues } from './RuleFormDialog';

interface CarrierSelectorProps {
  form: UseFormReturn<RuleFormValues>;
}

/**
 * Carrier selector for package delivery alert rules (Story P7-2.2).
 *
 * Displays checkboxes for each delivery carrier:
 * - FedEx, UPS, USPS, Amazon, DHL
 *
 * If no carriers are selected, the rule matches any carrier.
 */
export function CarrierSelector({ form }: CarrierSelectorProps) {
  const selectedCarriers = form.watch('conditions.carriers') || [];

  const handleToggle = (carrier: string) => {
    const current = form.getValues('conditions.carriers') || [];
    const updated = current.includes(carrier)
      ? current.filter((c: string) => c !== carrier)
      : [...current, carrier];
    // If all carriers are unchecked, set to undefined (any carrier)
    form.setValue('conditions.carriers', updated.length > 0 ? updated : undefined, { shouldValidate: true });
  };

  return (
    <div className="space-y-2">
      <Label>Delivery Carriers</Label>
      <p className="text-sm text-muted-foreground mb-2">
        Select specific carriers to match, or leave empty for any carrier
      </p>
      <div className="flex flex-wrap gap-3">
        {CARRIERS.map((carrier) => (
          <div key={carrier.value} className="flex items-center space-x-2">
            <Checkbox
              id={`carrier-${carrier.value}`}
              checked={selectedCarriers.includes(carrier.value)}
              onCheckedChange={() => handleToggle(carrier.value)}
              aria-label={`Select ${carrier.label}`}
            />
            <Label
              htmlFor={`carrier-${carrier.value}`}
              className="text-sm font-normal cursor-pointer"
            >
              {carrier.label}
            </Label>
          </div>
        ))}
      </div>
    </div>
  );
}
