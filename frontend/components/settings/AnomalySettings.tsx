/**
 * Anomaly Detection Settings Component (Story P4-7.3)
 *
 * Provides UI for configuring anomaly detection thresholds:
 * - Low/Medium threshold slider (default: 0.3)
 * - Medium/High threshold slider (default: 0.6)
 * - Enable/disable anomaly scoring
 *
 * Settings are persisted via the system settings API.
 */

'use client';

import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { Activity, Info, Loader2 } from 'lucide-react';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { apiClient } from '@/lib/api-client';

interface AnomalySettingsProps {
  className?: string;
}

interface AnomalyConfig {
  anomaly_enabled: boolean;
  anomaly_low_threshold: number;
  anomaly_high_threshold: number;
}

const DEFAULT_CONFIG: AnomalyConfig = {
  anomaly_enabled: true,
  anomaly_low_threshold: 0.3,
  anomaly_high_threshold: 0.6,
};

export function AnomalySettings({ className }: AnomalySettingsProps) {
  const [config, setConfig] = useState<AnomalyConfig>(DEFAULT_CONFIG);
  const [initialConfig, setInitialConfig] = useState<AnomalyConfig>(DEFAULT_CONFIG);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  // Load current settings on mount
  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setIsLoading(true);
      const settings = await apiClient.settings.get();
      const loaded: AnomalyConfig = {
        anomaly_enabled: settings.anomaly_enabled ?? DEFAULT_CONFIG.anomaly_enabled,
        anomaly_low_threshold: settings.anomaly_low_threshold ?? DEFAULT_CONFIG.anomaly_low_threshold,
        anomaly_high_threshold: settings.anomaly_high_threshold ?? DEFAULT_CONFIG.anomaly_high_threshold,
      };
      setConfig(loaded);
      setInitialConfig(loaded);
    } catch (error) {
      console.error('Failed to load anomaly settings:', error);
      // Use defaults on error
      setConfig(DEFAULT_CONFIG);
      setInitialConfig(DEFAULT_CONFIG);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      setIsSaving(true);
      await apiClient.settings.update({
        anomaly_enabled: config.anomaly_enabled,
        anomaly_low_threshold: config.anomaly_low_threshold,
        anomaly_high_threshold: config.anomaly_high_threshold,
      });
      setInitialConfig(config);
      toast.success('Anomaly detection settings saved');
    } catch (error) {
      console.error('Failed to save anomaly settings:', error);
      toast.error('Failed to save settings');
    } finally {
      setIsSaving(false);
    }
  };

  const handleReset = () => {
    setConfig(DEFAULT_CONFIG);
  };

  const isDirty =
    config.anomaly_enabled !== initialConfig.anomaly_enabled ||
    config.anomaly_low_threshold !== initialConfig.anomaly_low_threshold ||
    config.anomaly_high_threshold !== initialConfig.anomaly_high_threshold;

  // Ensure low < high threshold
  const handleLowThresholdChange = (value: number) => {
    setConfig((prev) => ({
      ...prev,
      anomaly_low_threshold: Math.min(value, prev.anomaly_high_threshold - 0.05),
    }));
  };

  const handleHighThresholdChange = (value: number) => {
    setConfig((prev) => ({
      ...prev,
      anomaly_high_threshold: Math.max(value, prev.anomaly_low_threshold + 0.05),
    }));
  };

  if (isLoading) {
    return (
      <Card className={className}>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-blue-500" />
          <CardTitle>Anomaly Detection</CardTitle>
        </div>
        <CardDescription>
          Configure how unusual activity is detected and classified based on baseline patterns
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Enable/Disable Toggle */}
        <div className="flex items-center justify-between p-3 rounded-lg border">
          <div className="flex-1">
            <Label htmlFor="anomaly-enabled" className="cursor-pointer">
              Enable Anomaly Detection
            </Label>
            <p className="text-xs text-muted-foreground">
              Score events based on deviation from normal activity patterns
            </p>
          </div>
          <Switch
            id="anomaly-enabled"
            checked={config.anomaly_enabled}
            onCheckedChange={(checked) =>
              setConfig((prev) => ({ ...prev, anomaly_enabled: checked }))
            }
          />
        </div>

        {/* Threshold Settings */}
        <div className={`space-y-6 ${!config.anomaly_enabled ? 'opacity-50 pointer-events-none' : ''}`}>
          {/* Visual Preview */}
          <div className="space-y-2">
            <Label>Severity Classification Preview</Label>
            <div className="relative h-8 rounded-lg overflow-hidden">
              {/* Low (green) */}
              <div
                className="absolute h-full bg-green-500/70"
                style={{ width: `${config.anomaly_low_threshold * 100}%` }}
              />
              {/* Medium (amber) */}
              <div
                className="absolute h-full bg-amber-500/70"
                style={{
                  left: `${config.anomaly_low_threshold * 100}%`,
                  width: `${(config.anomaly_high_threshold - config.anomaly_low_threshold) * 100}%`,
                }}
              />
              {/* High (red) */}
              <div
                className="absolute h-full bg-red-500/70"
                style={{
                  left: `${config.anomaly_high_threshold * 100}%`,
                  width: `${(1 - config.anomaly_high_threshold) * 100}%`,
                }}
              />
              {/* Labels */}
              <div className="absolute inset-0 flex">
                <div
                  className="flex items-center justify-center text-xs font-medium text-green-900"
                  style={{ width: `${config.anomaly_low_threshold * 100}%` }}
                >
                  Normal
                </div>
                <div
                  className="flex items-center justify-center text-xs font-medium text-amber-900"
                  style={{ width: `${(config.anomaly_high_threshold - config.anomaly_low_threshold) * 100}%` }}
                >
                  Unusual
                </div>
                <div
                  className="flex items-center justify-center text-xs font-medium text-red-900"
                  style={{ width: `${(1 - config.anomaly_high_threshold) * 100}%` }}
                >
                  Anomaly
                </div>
              </div>
            </div>
          </div>

          {/* Low Threshold Slider */}
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Label>Normal/Unusual Threshold</Label>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Info className="h-4 w-4 text-muted-foreground cursor-help" />
                </TooltipTrigger>
                <TooltipContent side="right" className="max-w-[250px]">
                  <p>
                    Events with anomaly scores below this threshold are considered normal activity.
                    Higher values mean more events are classified as normal.
                  </p>
                </TooltipContent>
              </Tooltip>
              <span className="ml-auto text-sm font-medium">
                {Math.round(config.anomaly_low_threshold * 100)}%
              </span>
            </div>
            <Slider
              value={[config.anomaly_low_threshold]}
              onValueChange={([value]) => handleLowThresholdChange(value)}
              min={0.1}
              max={0.9}
              step={0.05}
            />
            <div className="flex justify-between text-xs text-muted-foreground px-1">
              <span>10%</span>
              <span>Default: 30%</span>
              <span>90%</span>
            </div>
          </div>

          {/* High Threshold Slider */}
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Label>Unusual/Anomaly Threshold</Label>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Info className="h-4 w-4 text-muted-foreground cursor-help" />
                </TooltipTrigger>
                <TooltipContent side="right" className="max-w-[250px]">
                  <p>
                    Events with anomaly scores at or above this threshold are flagged as anomalies.
                    Lower values mean more events trigger anomaly alerts.
                  </p>
                </TooltipContent>
              </Tooltip>
              <span className="ml-auto text-sm font-medium">
                {Math.round(config.anomaly_high_threshold * 100)}%
              </span>
            </div>
            <Slider
              value={[config.anomaly_high_threshold]}
              onValueChange={([value]) => handleHighThresholdChange(value)}
              min={0.1}
              max={0.9}
              step={0.05}
            />
            <div className="flex justify-between text-xs text-muted-foreground px-1">
              <span>10%</span>
              <span>Default: 60%</span>
              <span>90%</span>
            </div>
          </div>

          {/* Explanation */}
          <div className="p-3 rounded-lg bg-muted text-sm space-y-2">
            <p className="font-medium">How Anomaly Scoring Works</p>
            <ul className="list-disc list-inside text-muted-foreground space-y-1 text-xs">
              <li>Events are scored based on time of day, day of week, and object types</li>
              <li>Scores indicate how unusual an event is compared to learned patterns</li>
              <li>Baseline patterns are built from the last 30 days of activity</li>
              <li>A minimum of 50 events per camera is needed for reliable scoring</li>
            </ul>
          </div>
        </div>

        {/* Actions */}
        <div className="flex justify-between pt-4 border-t">
          <Button
            type="button"
            variant="outline"
            onClick={handleReset}
            disabled={isSaving}
          >
            Reset to Defaults
          </Button>
          <Button
            type="button"
            onClick={handleSave}
            disabled={!isDirty || isSaving}
          >
            {isSaving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            Save Changes
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
