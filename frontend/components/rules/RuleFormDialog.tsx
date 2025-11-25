'use client';

/**
 * Rule Form Dialog - Create/Edit alert rules
 * Implements AC #2, #3, #5, #7
 */

import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { apiClient, ApiError } from '@/lib/api-client';
import type { IAlertRule, IAlertRuleCreate, IAlertRuleConditions, IAlertRuleActions } from '@/types/alert-rule';
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
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';

import { ObjectTypeSelector } from './ObjectTypeSelector';
import { CameraSelector } from './CameraSelector';
import { TimeRangePicker } from './TimeRangePicker';
import { DaysOfWeekSelector } from './DaysOfWeekSelector';
import { WebhookConfig } from './WebhookConfig';
import { RuleTestResults } from './RuleTestResults';

// Form values type (what we use in the form) - exported for sub-components
export interface RuleFormValues {
  name: string;
  is_enabled: boolean;
  conditions: {
    object_types?: string[];
    cameras?: string[];
    time_of_day?: { start: string; end: string } | null;
    days_of_week?: number[];
    min_confidence?: number;
  };
  actions: {
    dashboard_notification: boolean;
    webhook?: { url: string; headers?: Record<string, string> } | null;
  };
  cooldown_minutes: number;
}

// Form validation schema matching backend Pydantic validators
const ruleFormSchema = z.object({
  name: z.string().min(1, 'Rule name is required').max(200, 'Name must be 200 characters or less'),
  is_enabled: z.boolean(),
  conditions: z.object({
    object_types: z.array(z.string()).optional(),
    cameras: z.array(z.string()).optional(),
    time_of_day: z.object({
      start: z.string().regex(/^([01]\d|2[0-3]):([0-5]\d)$/, 'Invalid time format (HH:MM)'),
      end: z.string().regex(/^([01]\d|2[0-3]):([0-5]\d)$/, 'Invalid time format (HH:MM)'),
    }).optional().nullable(),
    days_of_week: z.array(z.number().min(1).max(7)).optional(),
    min_confidence: z.number().min(0).max(100).optional(),
  }),
  actions: z.object({
    dashboard_notification: z.boolean(),
    webhook: z.object({
      url: z.string().min(1, 'URL is required').url('Invalid URL'),
      headers: z.record(z.string(), z.string()).nullable().optional(),
    }).nullable().optional(),
  }),
  cooldown_minutes: z.number().min(0).max(1440),
});

interface RuleFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rule?: IAlertRule | null;
  onClose: () => void;
}

export function RuleFormDialog({ open, onOpenChange, rule, onClose }: RuleFormDialogProps) {
  const isEditing = !!rule;
  const queryClient = useQueryClient();

  // Default form values
  const defaultValues: Partial<RuleFormValues> = {
    name: '',
    is_enabled: true,
    conditions: {
      object_types: [],
      cameras: [],
      time_of_day: null,
      days_of_week: [1, 2, 3, 4, 5, 6, 7],
      min_confidence: 70,
    },
    actions: {
      dashboard_notification: true,
      webhook: null,
    },
    cooldown_minutes: 5,
  };

  const form = useForm<RuleFormValues>({
    resolver: zodResolver(ruleFormSchema),
    defaultValues,
  });

  // Reset form when rule changes
  useEffect(() => {
    if (rule) {
      form.reset({
        name: rule.name,
        is_enabled: rule.is_enabled,
        conditions: {
          object_types: rule.conditions.object_types || [],
          cameras: rule.conditions.cameras || [],
          time_of_day: rule.conditions.time_of_day || null,
          days_of_week: rule.conditions.days_of_week || [1, 2, 3, 4, 5, 6, 7],
          min_confidence: rule.conditions.min_confidence ?? 70,
        },
        actions: {
          dashboard_notification: rule.actions.dashboard_notification ?? true,
          webhook: rule.actions.webhook || null,
        },
        cooldown_minutes: rule.cooldown_minutes,
      });
    } else {
      form.reset(defaultValues);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rule, open]);

  // Create mutation
  const createMutation = useMutation({
    mutationFn: (data: IAlertRuleCreate) => apiClient.alertRules.create(data),
    onSuccess: (newRule) => {
      queryClient.invalidateQueries({ queryKey: ['alertRules'] });
      toast.success(`Rule "${newRule.name}" created successfully`);
      onClose();
    },
    onError: (error) => {
      const message = error instanceof ApiError ? error.message : 'Failed to create rule';
      toast.error(message);
    },
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: IAlertRuleCreate }) =>
      apiClient.alertRules.update(id, data),
    onSuccess: (updatedRule) => {
      queryClient.invalidateQueries({ queryKey: ['alertRules'] });
      toast.success(`Rule "${updatedRule.name}" updated successfully`);
      onClose();
    },
    onError: (error) => {
      const message = error instanceof ApiError ? error.message : 'Failed to update rule';
      toast.error(message);
    },
  });

  const isPending = createMutation.isPending || updateMutation.isPending;

  const onSubmit = (values: RuleFormValues) => {
    // Clean up conditions - remove empty/default values
    const conditions: IAlertRuleConditions = {};
    if (values.conditions.object_types && values.conditions.object_types.length > 0) {
      conditions.object_types = values.conditions.object_types;
    }
    if (values.conditions.cameras && values.conditions.cameras.length > 0) {
      conditions.cameras = values.conditions.cameras;
    }
    if (values.conditions.time_of_day) {
      conditions.time_of_day = values.conditions.time_of_day;
    }
    if (values.conditions.days_of_week && values.conditions.days_of_week.length > 0 && values.conditions.days_of_week.length < 7) {
      conditions.days_of_week = values.conditions.days_of_week;
    }
    if (values.conditions.min_confidence !== undefined && values.conditions.min_confidence > 0) {
      conditions.min_confidence = values.conditions.min_confidence;
    }

    // Clean up actions
    const actions: IAlertRuleActions = {
      dashboard_notification: values.actions.dashboard_notification,
    };
    // Only include webhook if it has a valid URL
    if (values.actions.webhook && values.actions.webhook.url) {
      actions.webhook = values.actions.webhook;
    }

    const data: IAlertRuleCreate = {
      name: values.name,
      is_enabled: values.is_enabled,
      conditions,
      actions,
      cooldown_minutes: values.cooldown_minutes,
    };

    if (isEditing && rule) {
      updateMutation.mutate({ id: rule.id, data });
    } else {
      createMutation.mutate(data);
    }
  };

  const handleCancel = () => {
    if (form.formState.isDirty) {
      // Confirm discard changes
      if (window.confirm('You have unsaved changes. Discard them?')) {
        onClose();
      }
    } else {
      onClose();
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit Alert Rule' : 'Create Alert Rule'}</DialogTitle>
          <DialogDescription>
            {isEditing
              ? 'Update the conditions and actions for this alert rule.'
              : 'Define when you want to receive notifications.'}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            {/* Basic Info */}
            <div className="space-y-4">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Rule Name</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="Package delivery alert"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="is_enabled"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-lg border p-3">
                    <div>
                      <FormLabel>Enabled</FormLabel>
                      <FormDescription>
                        Rule will trigger alerts when enabled
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
            </div>

            {/* Conditions Section */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Conditions</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <ObjectTypeSelector form={form} />
                <CameraSelector form={form} />
                <TimeRangePicker form={form} />
                <DaysOfWeekSelector form={form} />

                <FormField
                  control={form.control}
                  name="conditions.min_confidence"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Minimum Confidence: {field.value}%</FormLabel>
                      <FormControl>
                        <Slider
                          value={[field.value ?? 70]}
                          onValueChange={([value]) => field.onChange(value)}
                          min={0}
                          max={100}
                          step={5}
                          className="py-2"
                        />
                      </FormControl>
                      <FormDescription>
                        Only trigger for events with confidence above this threshold
                      </FormDescription>
                    </FormItem>
                  )}
                />

                {form.formState.errors.conditions?.root && (
                  <p className="text-sm text-destructive">
                    {form.formState.errors.conditions.root.message}
                  </p>
                )}
              </CardContent>
            </Card>

            {/* Actions Section */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Actions</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <FormField
                  control={form.control}
                  name="actions.dashboard_notification"
                  render={({ field }) => (
                    <FormItem className="flex items-center justify-between rounded-lg border p-3">
                      <div>
                        <FormLabel>Dashboard Notification</FormLabel>
                        <FormDescription>
                          Show notification in the dashboard
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

                <WebhookConfig form={form} />

                {form.formState.errors.actions?.root && (
                  <p className="text-sm text-destructive">
                    {form.formState.errors.actions.root.message}
                  </p>
                )}
              </CardContent>
            </Card>

            {/* Cooldown Section */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Cooldown</CardTitle>
              </CardHeader>
              <CardContent>
                <FormField
                  control={form.control}
                  name="cooldown_minutes"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Cooldown Period: {field.value} minute{field.value !== 1 ? 's' : ''}</FormLabel>
                      <FormControl>
                        <Slider
                          value={[field.value]}
                          onValueChange={([value]) => field.onChange(value)}
                          min={0}
                          max={60}
                          step={1}
                          className="py-2"
                        />
                      </FormControl>
                      <FormDescription>
                        Prevent repeated alerts for the same rule within this time period
                      </FormDescription>
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>

            {/* Test Rule Section - only for existing rules */}
            {isEditing && rule && (
              <RuleTestResults ruleId={rule.id} />
            )}

            <DialogFooter className="gap-2 sm:gap-0">
              <Button type="button" variant="outline" onClick={handleCancel}>
                Cancel
              </Button>
              <Button type="submit" disabled={isPending}>
                {isPending ? 'Saving...' : isEditing ? 'Update Rule' : 'Save Rule'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
