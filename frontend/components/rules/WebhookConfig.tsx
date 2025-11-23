'use client';

import { useState } from 'react';
import { UseFormReturn } from 'react-hook-form';
import { Plus, Trash2 } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import type { RuleFormValues } from './RuleFormDialog';

interface WebhookConfigProps {
  form: UseFormReturn<RuleFormValues>;
}

export function WebhookConfig({ form }: WebhookConfigProps) {
  const webhook = form.watch('actions.webhook');
  const [enabled, setEnabled] = useState(!!webhook);
  const [headers, setHeaders] = useState<Array<{ key: string; value: string }>>(
    webhook?.headers
      ? Object.entries(webhook.headers).map(([key, value]) => ({ key, value: value as string }))
      : []
  );

  const handleToggle = (checked: boolean) => {
    setEnabled(checked);
    if (checked) {
      form.setValue('actions.webhook', {
        url: '',
        headers: headers.length > 0
          ? Object.fromEntries(headers.filter(h => h.key).map(h => [h.key, h.value]))
          : undefined,
      }, { shouldValidate: true });
    } else {
      form.setValue('actions.webhook', null, { shouldValidate: true });
    }
  };

  const handleUrlChange = (url: string) => {
    const current = form.getValues('actions.webhook') || { url: '' };
    form.setValue('actions.webhook', { ...current, url }, { shouldValidate: true });
  };

  const handleAddHeader = () => {
    setHeaders([...headers, { key: '', value: '' }]);
  };

  const handleRemoveHeader = (index: number) => {
    const updated = headers.filter((_, i) => i !== index);
    setHeaders(updated);
    updateHeaders(updated);
  };

  const handleHeaderChange = (index: number, field: 'key' | 'value', value: string) => {
    const updated = headers.map((h, i) =>
      i === index ? { ...h, [field]: value } : h
    );
    setHeaders(updated);
    updateHeaders(updated);
  };

  const updateHeaders = (headersList: Array<{ key: string; value: string }>) => {
    const current = form.getValues('actions.webhook');
    if (current) {
      const headersObj = headersList.filter(h => h.key).length > 0
        ? Object.fromEntries(headersList.filter(h => h.key).map(h => [h.key, h.value]))
        : undefined;
      form.setValue('actions.webhook', { ...current, headers: headersObj }, { shouldValidate: true });
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between rounded-lg border p-3">
        <div>
          <Label>Webhook</Label>
          <p className="text-sm text-muted-foreground">
            Send HTTP POST request when rule triggers
          </p>
        </div>
        <Switch
          checked={enabled}
          onCheckedChange={handleToggle}
          aria-label="Enable webhook action"
        />
      </div>

      {enabled && (
        <div className="pl-4 space-y-4">
          <FormField
            control={form.control}
            name="actions.webhook.url"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Webhook URL</FormLabel>
                <FormControl>
                  <Input
                    type="url"
                    placeholder="https://example.com/webhook"
                    value={field.value || ''}
                    onChange={(e) => handleUrlChange(e.target.value)}
                  />
                </FormControl>
                <FormDescription>
                  Must be HTTPS in production
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Custom Headers (Optional)</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleAddHeader}
              >
                <Plus className="h-4 w-4 mr-1" />
                Add Header
              </Button>
            </div>
            <p className="text-sm text-muted-foreground">
              Add custom headers for authentication
            </p>

            {headers.map((header, index) => (
              <div key={index} className="flex gap-2 items-center">
                <Input
                  placeholder="Header name"
                  value={header.key}
                  onChange={(e) => handleHeaderChange(index, 'key', e.target.value)}
                  className="flex-1"
                  aria-label={`Header ${index + 1} name`}
                />
                <Input
                  placeholder="Header value"
                  value={header.value}
                  onChange={(e) => handleHeaderChange(index, 'value', e.target.value)}
                  className="flex-1"
                  aria-label={`Header ${index + 1} value`}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => handleRemoveHeader(index)}
                  aria-label={`Remove header ${index + 1}`}
                >
                  <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
