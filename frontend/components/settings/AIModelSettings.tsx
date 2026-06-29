/**
 * AI Model Settings
 *
 * Per-provider vision-model picker. Models get deprecated, so each provider
 * resolves a current model dynamically; this UI lets an admin see what's
 * available right now and optionally pin a specific model.
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import { Brain, Loader2, CheckCircle2, XCircle, RotateCcw } from 'lucide-react';
import { toast } from 'sonner';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { apiClient } from '@/lib/api-client';

interface ProviderModel {
  provider: string;
  configured: boolean;
  active_model: string | null;
  override: string | null;
  available_models: string[];
}

export function AIModelSettings() {
  const [providers, setProviders] = useState<ProviderModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [selected, setSelected] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.settings.getAIModels();
      setProviders(data.providers);
      setSelected(
        Object.fromEntries(
          data.providers.map((p) => [p.provider, p.override || p.active_model || '']),
        ),
      );
    } catch {
      toast.error('Failed to load AI models');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const updateModel = async (provider: string, model: string | null) => {
    setSaving(provider);
    try {
      await apiClient.settings.setAIModel(provider, model);
      toast.success(
        model
          ? `Pinned ${provider} to ${model}`
          : `${provider} reverted to dynamic resolution`,
      );
      await load();
    } catch {
      toast.error(`Failed to update ${provider}`);
    } finally {
      setSaving(null);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Brain className="h-5 w-5" /> AI Models
        </CardTitle>
        <CardDescription>
          Choose the vision model for each provider. Leave unpinned to automatically
          resolve a current, available model (recommended).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading ? (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading available models…
          </div>
        ) : (
          providers.map((p) => (
            <div
              key={p.provider}
              className="flex flex-col gap-3 rounded-lg border p-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="space-y-1">
                <div className="flex items-center gap-2 font-medium capitalize">
                  {p.configured ? (
                    <CheckCircle2 className="h-4 w-4 text-success" />
                  ) : (
                    <XCircle className="h-4 w-4 text-muted-foreground" />
                  )}
                  {p.provider}
                  {p.configured &&
                    (p.override ? (
                      <Badge variant="secondary">pinned</Badge>
                    ) : (
                      <Badge variant="outline">dynamic</Badge>
                    ))}
                </div>
                <div className="text-xs text-muted-foreground">
                  {p.configured ? (
                    <>
                      Active: <span className="font-mono">{p.active_model || '—'}</span>
                    </>
                  ) : (
                    'No API key configured'
                  )}
                </div>
              </div>

              {p.configured && (
                <div className="flex items-center gap-2">
                  <Select
                    value={selected[p.provider] || ''}
                    onValueChange={(v) =>
                      setSelected((s) => ({ ...s, [p.provider]: v }))
                    }
                  >
                    <SelectTrigger className="w-[280px]">
                      <SelectValue placeholder="Select a model" />
                    </SelectTrigger>
                    <SelectContent>
                      {p.available_models.length === 0 ? (
                        <SelectItem value="__none__" disabled>
                          (could not list models)
                        </SelectItem>
                      ) : (
                        p.available_models.map((m) => (
                          <SelectItem key={m} value={m}>
                            {m}
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                  <Button
                    size="sm"
                    disabled={
                      saving === p.provider ||
                      !selected[p.provider] ||
                      selected[p.provider] === p.override
                    }
                    onClick={() => updateModel(p.provider, selected[p.provider])}
                  >
                    {saving === p.provider ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      'Pin'
                    )}
                  </Button>
                  {p.override && (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={saving === p.provider}
                      onClick={() => updateModel(p.provider, null)}
                      title="Revert to dynamic resolution"
                    >
                      <RotateCcw className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}
