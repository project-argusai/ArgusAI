'use client';

import React, { useState, useEffect } from 'react';
import { apiClient } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { Loader2, RefreshCw, Save, RotateCcw } from 'lucide-react';
import { formatRelative } from '@/lib/datetime';

interface CircuitBreakerConfig {
  failure_threshold: number;
  recovery_timeout: number;
  half_open_max_calls: number;
  failure_rate_threshold: number;
  minimum_calls_in_window: number;
  window_duration_seconds: number;
}

interface CircuitBreakerStatus {
  provider: string;
  config: CircuitBreakerConfig;
  state: 'closed' | 'open' | 'half_open';
  failure_count: number;
  current_failure_rate: number | null;
  recent_window_size: number;
  last_failure_time: string | null;
  recent_transitions?: Array<{
    timestamp: number;
    from_state?: string;
    to_state?: string;
    reason?: string;
  }>;
}

interface AIResilienceData {
  default: CircuitBreakerStatus;
  openai?: CircuitBreakerStatus;
  grok?: CircuitBreakerStatus;
  claude?: CircuitBreakerStatus;
  gemini?: CircuitBreakerStatus;
}

const PROVIDERS = ['default', 'openai', 'grok', 'claude', 'gemini'] as const;

const STATE_COLORS = {
  closed: 'bg-green-100 text-green-800 border-green-200',
  open: 'bg-red-100 text-red-800 border-red-200',
  half_open: 'bg-yellow-100 text-yellow-800 border-yellow-200',
};

const STATE_LABELS = {
  closed: 'Closed (Healthy)',
  open: 'Open (Blocking)',
  half_open: 'Half-Open (Testing)',
};

export function AIResilienceSettings() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [resetting, setResetting] = useState<string | null>(null);
  const [resettingAll, setResettingAll] = useState(false);
  const [lastReset, setLastReset] = useState<string | null>(null);

  const fetchStatus = async () => {
    try {
      const res = await apiClient.getAIResilience();
      setData(res);
      if (res?.last_reset) {
        setLastReset(res.last_reset);
      }
    } catch (error) {
      console.error('Failed to load AI Resilience status:', error);
      toast.error('Failed to load AI Resilience configuration');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleSave = async (provider: string, config: CircuitBreakerConfig) => {
    setSaving(provider);
    try {
      await apiClient.updateAIResilienceConfig(provider, config);
      toast.success(`Circuit breaker config for ${provider} saved`);
      await fetchStatus();
    } catch (error: any) {
      toast.error(`Failed to save config for ${provider}`, {
        description: error?.message || 'Unknown error',
      });
    } finally {
      setSaving(null);
    }
  };

  const handleReset = async (provider: string) => {
    setResetting(provider);
    try {
      await apiClient.resetAICircuitBreaker(provider);
      toast.success(`Circuit breaker for ${provider} has been reset`);
      await fetchStatus();
    } catch (error) {
      toast.error(`Failed to reset ${provider}`);
    } finally {
      setResetting(null);
    }
  };

  const handleResetAll = async () => {
    if (!confirm("Reset ALL circuit breakers to CLOSED state?")) return;

    setResettingAll(true);
    try {
      await apiClient.resetAICircuitBreaker("default");
      toast.success("All circuit breakers have been reset to CLOSED");
      await fetchStatus();
    } catch (error) {
      toast.error("Failed to reset all breakers");
    } finally {
      setResettingAll(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  if (!data) {
    return <div className="text-red-500">Failed to load AI Resilience data.</div>;
  }

  const renderProviderCard = (provider: string, status?: CircuitBreakerStatus) => {
    if (!status) return null;

    const [localConfig, setLocalConfig] = useState<CircuitBreakerConfig>(status.config);

    const hasChanges = JSON.stringify(localConfig) !== JSON.stringify(status.config);

    return (
      <Card key={provider} className="mb-6">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <div>
            <CardTitle className="capitalize">{provider} Circuit Breaker</CardTitle>
            <CardDescription>Failure detection and recovery settings</CardDescription>
          </div>
          <Badge className={STATE_COLORS[status.state]}>
            {STATE_LABELS[status.state]}
          </Badge>
        </CardHeader>

        <CardContent className="space-y-6">
          {/* Live Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <div className="text-muted-foreground">State</div>
              <div className="font-medium capitalize">{status.state}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Failure Count</div>
              <div className="font-medium">{status.failure_count}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Failure Rate</div>
              <div className="font-medium">
                {status.current_failure_rate !== null 
                  ? `${(status.current_failure_rate * 100).toFixed(1)}%` 
                  : 'N/A'}
              </div>
            </div>
            <div>
              <div className="text-muted-foreground">Window Size</div>
              <div className="font-medium">{status.recent_window_size} calls</div>
            </div>
          </div>

          {/* Config Form */}
          <div className="space-y-4">
            <div className="text-sm font-medium">Configuration</div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <Label>Failure Threshold (consecutive)</Label>
                <Input
                  type="number"
                  value={localConfig.failure_threshold}
                  onChange={(e) => setLocalConfig({ ...localConfig, failure_threshold: parseInt(e.target.value) || 5 })}
                />
              </div>

              <div>
                <Label>Recovery Timeout (seconds)</Label>
                <Input
                  type="number"
                  step="1"
                  value={localConfig.recovery_timeout}
                  onChange={(e) => setLocalConfig({ ...localConfig, recovery_timeout: parseFloat(e.target.value) || 90 })}
                />
              </div>

              <div>
                <Label>Failure Rate Threshold</Label>
                <Input
                  type="number"
                  step="0.05"
                  value={localConfig.failure_rate_threshold}
                  onChange={(e) => setLocalConfig({ ...localConfig, failure_rate_threshold: parseFloat(e.target.value) || 0.5 })}
                />
              </div>

              <div>
                <Label>Window Duration (seconds)</Label>
                <Input
                  type="number"
                  value={localConfig.window_duration_seconds}
                  onChange={(e) => setLocalConfig({ ...localConfig, window_duration_seconds: parseFloat(e.target.value) || 60 })}
                />
              </div>

              <div>
                <Label>Min Calls in Window</Label>
                <Input
                  type="number"
                  value={localConfig.minimum_calls_in_window}
                  onChange={(e) => setLocalConfig({ ...localConfig, minimum_calls_in_window: parseInt(e.target.value) || 6 })}
                />
              </div>

              <div>
                <Label>Half-Open Max Calls</Label>
                <Input
                  type="number"
                  value={localConfig.half_open_max_calls}
                  onChange={(e) => setLocalConfig({ ...localConfig, half_open_max_calls: parseInt(e.target.value) || 1 })}
                />
              </div>
            </div>
          </div>

          <div className="flex gap-2 pt-2">
            <Button
              onClick={() => handleSave(provider, localConfig)}
              disabled={!hasChanges || saving === provider}
              className="flex-1"
            >
              {saving === provider ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-2 h-4 w-4" />
              )}
              Save Configuration
            </Button>

            <Button
              variant="outline"
              onClick={() => handleReset(provider)}
              disabled={resetting === provider}
            >
              {resetting === provider ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <RotateCcw className="mr-2 h-4 w-4" />
              )}
              Reset Breaker
            </Button>
          </div>

          {hasChanges && (
            <p className="text-xs text-muted-foreground">You have unsaved changes.</p>
          )}

          {/* Recent Transitions History */}
          {status.recent_transitions && status.recent_transitions.length > 0 && (
            <details className="mt-4">
              <summary className="cursor-pointer text-sm font-medium text-muted-foreground hover:text-foreground">
                Recent Transitions ({status.recent_transitions.length})
              </summary>
              <div className="mt-2 max-h-48 overflow-auto rounded-md border bg-muted/30 p-3 text-xs">
                <table className="w-full">
                  <thead>
                    <tr className="text-left text-muted-foreground">
                      <th className="pb-1">Time</th>
                      <th className="pb-1">From → To</th>
                      <th className="pb-1">Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {status.recent_transitions.slice(0, 8).map((t: any, idx: number) => (
                      <tr key={idx} className="border-t">
                        <td className="py-1 font-mono text-[10px]">
                          {new Date(t.timestamp * 1000).toLocaleTimeString()}
                        </td>
                        <td className="py-1">
                          <span className="font-medium">{t.from_state}</span> → <span className="font-medium">{t.to_state}</span>
                        </td>
                        <td className="py-1 text-muted-foreground">{t.reason || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
        </CardContent>
      </Card>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-lg font-medium">AI Resilience</h3>
          <p className="text-sm text-muted-foreground">
            Configure circuit breaker behavior for each AI provider. Changes take effect immediately after saving.
            {lastReset && (
              <span className="ml-2 text-xs text-muted-foreground">
                Last reset: {formatRelative(lastReset)}
              </span>
            )}
          </p>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={handleResetAll}
          disabled={resettingAll || loading}
          className="shrink-0"
        >
          {resettingAll ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <RotateCcw className="mr-2 h-4 w-4" />
          )}
          Reset All Breakers
        </Button>
      </div>

      {renderProviderCard('default', data.default)}
      {renderProviderCard('openai', data.openai)}
      {renderProviderCard('grok', data.grok)}
      {renderProviderCard('claude', data.claude)}
      {renderProviderCard('gemini', data.gemini)}

      <div className="flex justify-end">
        <Button variant="outline" onClick={fetchStatus}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh Status
        </Button>
      </div>
    </div>
  );
}
