'use client';

/**
 * Entity Rule Selector - Entity-based alert filtering (Story P12-1.3)
 *
 * Provides UI for selecting entity match mode and specific entity:
 * - 'any': No entity filter (default)
 * - 'specific': Trigger only for a selected entity
 * - 'unknown': Trigger only for unrecognized entities (stranger detection)
 */

import { useQuery } from '@tanstack/react-query';
import { UseFormReturn } from 'react-hook-form';
import { User, UserX, Users } from 'lucide-react';

import { apiClient } from '@/lib/api-client';
import { getEntityDisplayName } from '@/lib/entity-display-name';
import { ENTITY_MATCH_MODES } from '@/types/alert-rule';
import type { RuleFormValues } from './RuleFormDialog';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';

interface EntityRuleSelectorProps {
  form: UseFormReturn<RuleFormValues>;
}

// Icon mapping for entity match modes
const MODE_ICONS = {
  any: Users,
  specific: User,
  unknown: UserX,
} as const;

export function EntityRuleSelector({ form }: EntityRuleSelectorProps) {
  const entityMatchMode = form.watch('entity_match_mode') || 'any';

  // Fetch entities for the dropdown
  const { data: entitiesData, isLoading: isLoadingEntities } = useQuery({
    queryKey: ['entities', 'for-rules'],
    queryFn: async () => {
      const response = await apiClient.entities.list({ limit: 100, named_only: true });
      return response.entities;
    },
    staleTime: 30000, // 30 seconds
  });

  return (
    <div className="space-y-4">
      {/* Entity Match Mode Selection */}
      <FormField
        control={form.control}
        name="entity_match_mode"
        render={({ field }) => (
          <FormItem className="space-y-3">
            <FormLabel>Entity Filter</FormLabel>
            <FormControl>
              <RadioGroup
                onValueChange={field.onChange}
                value={field.value || 'any'}
                className="grid grid-cols-1 gap-2 sm:grid-cols-3"
              >
                {ENTITY_MATCH_MODES.map((mode) => {
                  const Icon = MODE_ICONS[mode.value as keyof typeof MODE_ICONS];
                  return (
                    <Label
                      key={mode.value}
                      htmlFor={`entity-mode-${mode.value}`}
                      className={`
                        flex items-center gap-3 rounded-lg border p-3 cursor-pointer
                        transition-colors hover:bg-accent
                        ${field.value === mode.value ? 'border-primary bg-accent' : 'border-muted'}
                      `}
                    >
                      <RadioGroupItem
                        value={mode.value}
                        id={`entity-mode-${mode.value}`}
                        className="sr-only"
                      />
                      <Icon className="h-4 w-4 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm">{mode.label}</div>
                        <div className="text-xs text-muted-foreground truncate">
                          {mode.description}
                        </div>
                      </div>
                    </Label>
                  );
                })}
              </RadioGroup>
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      {/* Entity Selection Dropdown - Only show for 'specific' mode */}
      {entityMatchMode === 'specific' && (
        <FormField
          control={form.control}
          name="entity_id"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Select Entity</FormLabel>
              <FormControl>
                {isLoadingEntities ? (
                  <Skeleton className="h-10 w-full" />
                ) : (
                  <Select
                    onValueChange={field.onChange}
                    value={field.value || ''}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Choose an entity..." />
                    </SelectTrigger>
                    <SelectContent>
                      {entitiesData && entitiesData.length > 0 ? (
                        entitiesData.map((entity) => (
                          <SelectItem key={entity.id} value={entity.id}>
                            <div className="flex items-center gap-2">
                              <span className="capitalize text-xs text-muted-foreground">
                                [{entity.entity_type}]
                              </span>
                              <span>{getEntityDisplayName(entity)}</span>
                              <span className="text-xs text-muted-foreground">
                                ({entity.occurrence_count} visits)
                              </span>
                            </div>
                          </SelectItem>
                        ))
                      ) : (
                        <SelectItem value="" disabled>
                          No named entities found
                        </SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                )}
              </FormControl>
              <FormDescription>
                Only events matching this entity will trigger the alert
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
      )}

      {/* Helpful description for stranger detection mode */}
      {entityMatchMode === 'unknown' && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950">
          <p className="text-sm text-amber-800 dark:text-amber-200">
            Stranger Detection Mode: This rule will only trigger when a person or vehicle
            is detected that doesn&apos;t match any recognized entity in your system.
          </p>
        </div>
      )}
    </div>
  );
}
