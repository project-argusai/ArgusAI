'use client';

/**
 * #675 / #720: toggle for one notification per grouped incident (#719).
 *
 * Stored as `notify_per_incident` through the existing system settings API.
 * Default is off; a missing or unreadable value reads as off.
 */
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api-client';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export const NOTIFY_PER_INCIDENT_KEY = 'notify_per_incident' as const;

/** Only a real `true` turns it on; anything else is off. */
export function readNotifyPerIncident(settings: unknown): boolean {
  if (!settings || typeof settings !== 'object') return false;
  return (settings as Record<string, unknown>)[NOTIFY_PER_INCIDENT_KEY] === true;
}

export function IncidentNotificationSetting() {
  const [enabled, setEnabled] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let active = true;
    apiClient.settings
      .get()
      .then((s) => active && setEnabled(readNotifyPerIncident(s)))
      .catch(() => {
        if (!active) return;
        // Don't let a save overwrite a stored value we couldn't read.
        setEnabled(false);
        setLoadError(true);
      })
      .finally(() => active && setLoaded(true));
    return () => {
      active = false;
    };
  }, []);

  const onChange = async (checked: boolean) => {
    setSaving(true);
    try {
      await apiClient.settings.update({ [NOTIFY_PER_INCIDENT_KEY]: checked });
      setEnabled(checked);
      toast.success('Notification setting saved');
    } catch {
      toast.error('Failed to save setting');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Grouped incidents</CardTitle>
        <CardDescription>
          Events seen by several cameras at about the same time are grouped into one incident.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between gap-4">
          <div className="space-y-0.5">
            <Label htmlFor="notify-per-incident" className="text-sm font-medium">
              Send one notification per grouped incident
            </Label>
            <p className="text-xs text-muted-foreground">
              Off by default: each camera sends its own notification, as it does today.
            </p>
            {loadError && (
              <p role="alert" className="text-xs text-destructive">
                Couldn&apos;t load this setting. Reload the page to try again.
              </p>
            )}
          </div>
          <Switch
            id="notify-per-incident"
            checked={enabled}
            disabled={!loaded || saving || loadError}
            onCheckedChange={onChange}
          />
        </div>
      </CardContent>
    </Card>
  );
}
