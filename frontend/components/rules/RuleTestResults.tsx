'use client';

import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { FlaskConical, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

import { apiClient, ApiError } from '@/lib/api-client';
import type { IAlertRuleTestResponse } from '@/types/alert-rule';
import type { IEvent } from '@/types/event';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

interface RuleTestResultsProps {
  ruleId: string;
}

export function RuleTestResults({ ruleId }: RuleTestResultsProps) {
  const [testResult, setTestResult] = useState<IAlertRuleTestResponse | null>(null);
  const [hasTestedOnce, setHasTestedOnce] = useState(false);

  // Test mutation
  const testMutation = useMutation({
    mutationFn: () => apiClient.alertRules.test(ruleId, { limit: 50 }),
    onSuccess: (result) => {
      setTestResult(result);
      setHasTestedOnce(true);
    },
  });

  // Fetch matching events for display (only when we have matching IDs)
  const { data: matchingEvents } = useQuery({
    queryKey: ['events', 'test-matches', testResult?.matching_event_ids],
    queryFn: async () => {
      if (!testResult?.matching_event_ids.length) return [];
      // Fetch first 5 matching events for preview
      const eventPromises = testResult.matching_event_ids.slice(0, 5).map(id =>
        apiClient.events.getById(id).catch(() => null)
      );
      const events = await Promise.all(eventPromises);
      return events.filter((e): e is IEvent => e !== null);
    },
    enabled: !!testResult?.matching_event_ids.length,
  });

  const handleTest = () => {
    testMutation.mutate();
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <FlaskConical className="h-4 w-4" />
              Test Rule
            </CardTitle>
            <CardDescription>
              Test this rule against recent events
            </CardDescription>
          </div>
          <Button
            type="button"
            variant="outline"
            onClick={handleTest}
            disabled={testMutation.isPending}
          >
            {testMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Testing...
              </>
            ) : (
              'Test Rule'
            )}
          </Button>
        </div>
      </CardHeader>

      {(testResult || testMutation.isError) && (
        <CardContent className="pt-0">
          {testMutation.isError && (
            <div className="flex items-center gap-2 text-destructive">
              <AlertCircle className="h-4 w-4" />
              <span className="text-sm">
                {testMutation.error instanceof ApiError
                  ? testMutation.error.message
                  : 'Failed to test rule'}
              </span>
            </div>
          )}

          {testResult && (
            <div className="space-y-4">
              {/* Summary */}
              <div className="flex items-center gap-4 p-3 rounded-lg bg-muted/50">
                <div className="flex items-center gap-2">
                  {testResult.events_matched > 0 ? (
                    <CheckCircle className="h-5 w-5 text-green-500" />
                  ) : (
                    <AlertCircle className="h-5 w-5 text-yellow-500" />
                  )}
                  <span className="font-medium">
                    This rule would match {testResult.events_matched} of {testResult.events_tested} events
                  </span>
                </div>
              </div>

              {/* Matching events preview */}
              {matchingEvents && matchingEvents.length > 0 && (
                <div className="space-y-2">
                  <p className="text-sm font-medium">Matching Events:</p>
                  <div className="space-y-2">
                    {matchingEvents.map((event) => (
                      <div
                        key={event.id}
                        className="flex items-start justify-between p-2 rounded border bg-background gap-2"
                      >
                        <div className="flex-1 min-w-0">
                          <p className="text-sm break-words">{event.description || 'No description'}</p>
                          <p className="text-xs text-muted-foreground">
                            {formatDistanceToNow(new Date(event.timestamp), { addSuffix: true })}
                          </p>
                        </div>
                        <div className="flex items-center gap-2 ml-2">
                          <Badge variant="outline" className="text-xs">
                            {event.confidence}% confidence
                          </Badge>
                        </div>
                      </div>
                    ))}
                    {testResult.events_matched > 5 && (
                      <p className="text-xs text-muted-foreground text-center">
                        ... and {testResult.events_matched - 5} more
                      </p>
                    )}
                  </div>
                </div>
              )}

              {testResult.events_matched === 0 && hasTestedOnce && (
                <p className="text-sm text-muted-foreground">
                  No recent events match this rule&apos;s conditions. Try adjusting the conditions or wait for new events.
                </p>
              )}
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}
