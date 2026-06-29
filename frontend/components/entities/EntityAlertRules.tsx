'use client';

/**
 * EntityAlertRules - Display alert rules targeting a specific entity (Story P12-1.5)
 *
 * Shows all alert rules configured with entity_match_mode='specific' that target
 * the given entity. Displayed in the entity detail view.
 */

import { useQuery } from '@tanstack/react-query';
import { formatRelative } from '@/lib/datetime';
import { Bell, BellOff, Clock, AlertTriangle } from 'lucide-react';
import Link from 'next/link';

import { apiClient } from '@/lib/api-client';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

interface EntityAlertRulesProps {
  entityId: string;
}

export function EntityAlertRules({ entityId }: EntityAlertRulesProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['entity-alert-rules', entityId],
    queryFn: () => apiClient.entities.getAlertRules(entityId),
    staleTime: 30000, // 30 seconds
  });

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-sm text-muted-foreground flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-destructive" />
        Failed to load alert rules
      </div>
    );
  }

  if (!data || data.rules.length === 0) {
    return (
      <div className="text-sm text-muted-foreground py-4 text-center">
        <Bell className="h-8 w-8 mx-auto mb-2 opacity-30" />
        <p>No alert rules configured for this entity</p>
        <Link href="/rules" className="text-primary hover:underline text-xs mt-1 inline-block">
          Create an alert rule
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {data.rules.map((rule) => (
        <div
          key={rule.id}
          className="flex items-center justify-between p-3 rounded-lg border bg-card text-card-foreground"
        >
          <div className="flex items-center gap-3 min-w-0">
            {rule.is_enabled ? (
              <Bell className="h-4 w-4 text-primary flex-shrink-0" />
            ) : (
              <BellOff className="h-4 w-4 text-muted-foreground flex-shrink-0" />
            )}
            <div className="min-w-0">
              <p className="font-medium text-sm truncate">{rule.name}</p>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Clock className="h-3 w-3" />
                <span>{rule.cooldown_minutes}min cooldown</span>
                {rule.trigger_count > 0 && (
                  <span>| {rule.trigger_count} triggers</span>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <Badge variant={rule.is_enabled ? 'default' : 'secondary'}>
              {rule.is_enabled ? 'Active' : 'Disabled'}
            </Badge>
            {rule.last_triggered_at && (
              <span className="text-xs text-muted-foreground hidden sm:inline">
                {formatRelative(rule.last_triggered_at)}
              </span>
            )}
          </div>
        </div>
      ))}
      <div className="pt-2 text-center">
        <Link href="/rules">
          <Button variant="outline" size="sm">
            Manage Alert Rules
          </Button>
        </Link>
      </div>
    </div>
  );
}
