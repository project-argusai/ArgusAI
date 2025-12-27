'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { formatDistanceToNow } from 'date-fns';
import { Bell, Plus, Pencil, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { apiClient, ApiError } from '@/lib/api-client';
import type { IAlertRule } from '@/types/alert-rule';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/common/EmptyState';
import { ConditionsSummary } from './ConditionsSummary';

interface RulesListProps {
  onCreateRule: () => void;
  onEditRule: (rule: IAlertRule) => void;
  onDeleteRule: (rule: IAlertRule) => void;
}

export function RulesList({ onCreateRule, onEditRule, onDeleteRule }: RulesListProps) {
  const queryClient = useQueryClient();

  // Fetch alert rules
  const {
    data: rulesResponse,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ['alertRules'],
    queryFn: () => apiClient.alertRules.list(),
  });

  // Toggle enabled mutation with optimistic update
  const toggleEnabledMutation = useMutation({
    mutationFn: async ({ id, is_enabled }: { id: string; is_enabled: boolean }) => {
      return apiClient.alertRules.update(Number(id), { is_enabled });
    },
    onMutate: async ({ id, is_enabled }) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: ['alertRules'] });

      // Snapshot previous value
      const previousRules = queryClient.getQueryData(['alertRules']);

      // Optimistically update
      queryClient.setQueryData(['alertRules'], (old: { data: IAlertRule[]; total_count: number } | undefined) => {
        if (!old) return old;
        return {
          ...old,
          data: old.data.map((rule) =>
            rule.id === id ? { ...rule, is_enabled } : rule
          ),
        };
      });

      return { previousRules };
    },
    onError: (err, _variables, context) => {
      // Rollback on error
      if (context?.previousRules) {
        queryClient.setQueryData(['alertRules'], context.previousRules);
      }
      const message = err instanceof ApiError ? err.message : 'Failed to update rule';
      toast.error(message);
    },
    onSuccess: (updatedRule) => {
      toast.success(`Rule "${updatedRule.name}" ${updatedRule.is_enabled ? 'enabled' : 'disabled'}`);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['alertRules'] });
    },
  });

  const handleToggleEnabled = (rule: IAlertRule) => {
    toggleEnabledMutation.mutate({ id: rule.id, is_enabled: !rule.is_enabled });
  };

  // Loading state
  if (isLoading) {
    return <RulesListSkeleton />;
  }

  // Error state
  if (isError) {
    const errorMessage = error instanceof ApiError ? error.message : 'Failed to load alert rules';
    return (
      <Card>
        <CardContent className="py-12">
          <div className="text-center text-destructive">
            <p className="font-medium">Error loading alert rules</p>
            <p className="text-sm text-muted-foreground mt-1">{errorMessage}</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const rules = rulesResponse?.data || [];

  // Empty state
  if (rules.length === 0) {
    return (
      <EmptyState
        icon={<Bell className="h-12 w-12 text-muted-foreground" />}
        title="Create your first alert rule to get notified"
        description="Alert rules let you define conditions to trigger notifications when specific events occur."
        action={{
          label: 'Create Rule',
          onClick: onCreateRule,
        }}
      />
    );
  }

  return (
    <div className="space-y-4">
      {/* Header with Create button */}
      <div className="flex justify-between items-center">
        <div>
          <p className="text-sm text-muted-foreground">
            {rules.length} rule{rules.length !== 1 ? 's' : ''} configured
          </p>
        </div>
        <Button onClick={onCreateRule}>
          <Plus className="mr-2 h-4 w-4" />
          Create Rule
        </Button>
      </div>

      {/* Rules table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="text-left p-4 font-medium">Name</th>
                <th className="text-left p-4 font-medium">Status</th>
                <th className="text-left p-4 font-medium hidden md:table-cell">Conditions</th>
                <th className="text-left p-4 font-medium hidden lg:table-cell">Last Triggered</th>
                <th className="text-left p-4 font-medium hidden lg:table-cell">Actions</th>
                <th className="text-right p-4 font-medium">Manage</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((rule) => (
                <RuleRow
                  key={rule.id}
                  rule={rule}
                  onToggleEnabled={handleToggleEnabled}
                  onEdit={onEditRule}
                  onDelete={onDeleteRule}
                  isToggling={toggleEnabledMutation.isPending && toggleEnabledMutation.variables?.id === rule.id}
                />
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

interface RuleRowProps {
  rule: IAlertRule;
  onToggleEnabled: (rule: IAlertRule) => void;
  onEdit: (rule: IAlertRule) => void;
  onDelete: (rule: IAlertRule) => void;
  isToggling: boolean;
}

function RuleRow({ rule, onToggleEnabled, onEdit, onDelete, isToggling }: RuleRowProps) {
  // Format last triggered time
  const lastTriggeredText = rule.last_triggered_at
    ? formatDistanceToNow(new Date(rule.last_triggered_at), { addSuffix: true })
    : 'Never';

  // Get action badges
  const actionBadges = [];
  if (rule.actions.dashboard_notification) {
    actionBadges.push('Dashboard');
  }
  if (rule.actions.webhook) {
    actionBadges.push('Webhook');
  }

  return (
    <tr className="border-b hover:bg-muted/50 transition-colors">
      {/* Name */}
      <td className="p-4">
        <div className="font-medium">{rule.name}</div>
        {/* Show entity info if this is an entity-specific rule */}
        {rule.entity_match_mode === 'specific' && rule.entity_name && (
          <div className="text-xs text-muted-foreground mt-1">
            <Badge variant="secondary" className="text-xs">
              Entity: {rule.entity_name}
            </Badge>
          </div>
        )}
        {rule.entity_match_mode === 'unknown' && (
          <div className="text-xs text-muted-foreground mt-1">
            <Badge variant="secondary" className="text-xs">
              Strangers only
            </Badge>
          </div>
        )}
        {rule.trigger_count > 0 && (
          <div className="text-xs text-muted-foreground mt-1">
            Triggered {rule.trigger_count} time{rule.trigger_count !== 1 ? 's' : ''}
          </div>
        )}
      </td>

      {/* Status toggle */}
      <td className="p-4">
        <div className="flex items-center gap-2">
          <Switch
            checked={rule.is_enabled}
            onCheckedChange={() => onToggleEnabled(rule)}
            disabled={isToggling}
            aria-label={`${rule.is_enabled ? 'Disable' : 'Enable'} rule "${rule.name}"`}
          />
          <span className="text-sm text-muted-foreground">
            {rule.is_enabled ? 'Enabled' : 'Disabled'}
          </span>
        </div>
      </td>

      {/* Conditions summary (hidden on mobile) */}
      <td className="p-4 hidden md:table-cell">
        <ConditionsSummary conditions={rule.conditions} />
      </td>

      {/* Last triggered (hidden on small screens) */}
      <td className="p-4 hidden lg:table-cell">
        <span className="text-sm text-muted-foreground">{lastTriggeredText}</span>
      </td>

      {/* Actions (hidden on small screens) */}
      <td className="p-4 hidden lg:table-cell">
        <div className="flex flex-wrap gap-1">
          {actionBadges.map((action) => (
            <Badge key={action} variant="secondary" className="text-xs">
              {action}
            </Badge>
          ))}
        </div>
      </td>

      {/* Edit/Delete actions */}
      <td className="p-4">
        <div className="flex justify-end gap-2">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onEdit(rule)}
            aria-label={`Edit rule "${rule.name}"`}
          >
            <Pencil className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onDelete(rule)}
            aria-label={`Delete rule "${rule.name}"`}
            className="text-destructive hover:text-destructive"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </td>
    </tr>
  );
}

function RulesListSkeleton() {
  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-10 w-32" />
      </div>
      <Card>
        <div className="p-4 space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex items-center gap-4">
              <Skeleton className="h-6 w-48" />
              <Skeleton className="h-6 w-16" />
              <Skeleton className="h-6 w-32 hidden md:block" />
              <Skeleton className="h-6 w-24 hidden lg:block" />
              <div className="flex-1" />
              <Skeleton className="h-8 w-20" />
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
