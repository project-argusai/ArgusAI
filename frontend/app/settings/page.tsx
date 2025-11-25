/**
 * System Settings Page
 * Centralized settings management with tabbed interface
 * Story 4.4: Build System Settings Page
 */

'use client';

import { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import {
  Settings,
  Globe,
  Brain,
  Eye,
  Database,
  Loader2,
  CheckCircle2,
  XCircle,
  EyeOff,
  RotateCcw,
  Download,
  Trash2,
} from 'lucide-react';

import { apiClient } from '@/lib/api-client';
import { completeSettingsSchema } from '@/lib/settings-validation';
import type { SystemSettings, StorageStats } from '@/types/settings';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { ConfirmDialog } from '@/components/settings/ConfirmDialog';
import { BackupRestore } from '@/components/settings/BackupRestore';

const DEFAULT_PROMPT = 'Describe what you see in this image in one concise sentence. Focus on objects, people, and actions.';

export default function SettingsPage() {
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isTestingKey, setIsTestingKey] = useState(false);
  const [keyTestResult, setKeyTestResult] = useState<{ valid: boolean; error?: string } | null>(null);
  const [showApiKey, setShowApiKey] = useState(false);
  const [storageStats, setStorageStats] = useState<StorageStats | null>(null);
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean;
    title: string;
    description: string;
    onConfirm: () => void | Promise<void>;
    variant?: 'destructive' | 'default';
    requireCheckbox?: boolean;
  }>({
    open: false,
    title: '',
    description: '',
    onConfirm: () => {},
  });

  const form = useForm<SystemSettings>({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    resolver: zodResolver(completeSettingsSchema) as any,
    defaultValues: {
      system_name: 'Live Object AI Classifier',
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      language: 'English',
      date_format: 'MM/DD/YYYY',
      time_format: '12h',
      primary_model: 'gpt-4o-mini',
      primary_api_key: '',
      fallback_model: null,
      description_prompt: DEFAULT_PROMPT,
      motion_sensitivity: 50,
      detection_method: 'background_subtraction',
      cooldown_period: 60,
      min_motion_area: 5,
      save_debug_images: false,
      retention_days: 30,
      thumbnail_storage: 'filesystem',
      auto_cleanup: true,
    },
  });

  const { formState: { isDirty, dirtyFields, errors } } = form;

  // Log validation errors for debugging
  useEffect(() => {
    if (Object.keys(errors).length > 0) {
      console.error('Form validation errors:', errors);
    }
  }, [errors]);

  // Load settings on mount
  useEffect(() => {
    loadSettings();
    loadStorageStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadSettings = async () => {
    try {
      setIsLoading(true);
      const settings = await apiClient.settings.get();
      form.reset(settings);
    } catch (error) {
      console.error('Failed to load settings:', error);
      toast.error('Failed to load settings. Using defaults.');
    } finally {
      setIsLoading(false);
    }
  };

  const loadStorageStats = async () => {
    try {
      const stats = await apiClient.settings.getStorageStats();
      setStorageStats(stats);
    } catch (error) {
      console.error('Failed to load storage stats:', error);
    }
  };

  const handleSave = async (data: SystemSettings) => {
    try {
      setIsSaving(true);

      // Only send dirty (changed) fields
      const changedData: Partial<SystemSettings> = {};
      Object.keys(dirtyFields).forEach((key) => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (changedData as any)[key] = (data as any)[key];
      });

      const updated = await apiClient.settings.update(changedData);
      form.reset(updated); // Reset form with new data to clear dirty state
      toast.success(`Settings saved successfully at ${new Date().toLocaleTimeString()}`);
    } catch (error) {
      console.error('Failed to save settings:', error);
      toast.error('Failed to save settings. Please try again.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    form.reset();
    toast.info('Changes cancelled');
  };

  const handleTestApiKey = async () => {
    try {
      setIsTestingKey(true);
      setKeyTestResult(null);

      const model = form.getValues('primary_model');
      const apiKey = form.getValues('primary_api_key');

      if (!apiKey) {
        toast.error('API key is required');
        return;
      }

      // Skip test if API key is masked (already saved and encrypted)
      if (apiKey.startsWith('****')) {
        toast.info('Enter a new API key to test');
        return;
      }

      // Map model to provider
      const providerMap: Record<string, 'openai' | 'anthropic' | 'google'> = {
        'gpt-4o-mini': 'openai',
        'claude-3-haiku': 'anthropic',
        'gemini-flash': 'google',
      };
      const provider = providerMap[model];

      if (!provider) {
        toast.error('Unknown model provider');
        return;
      }

      const result = await apiClient.settings.testApiKey({ provider, api_key: apiKey });
      setKeyTestResult({ valid: result.valid, error: result.valid ? undefined : result.message });

      if (result.valid) {
        toast.success(result.message || 'API key is valid');
      } else {
        toast.error(result.message || 'API key validation failed');
      }

      // Clear result after 3 seconds
      setTimeout(() => setKeyTestResult(null), 3000);
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Connection failed, check your internet';
      setKeyTestResult({ valid: false, error: errorMessage });
      toast.error(errorMessage);
    } finally {
      setIsTestingKey(false);
    }
  };

  const handleResetPrompt = () => {
    setConfirmDialog({
      open: true,
      title: 'Restore default AI description prompt?',
      description: 'This will replace your custom prompt with the default prompt.',
      onConfirm: () => {
        form.setValue('description_prompt', DEFAULT_PROMPT, { shouldDirty: true });
        setConfirmDialog({ ...confirmDialog, open: false });
        toast.success('Prompt reset to default');
      },
    });
  };

  const handleExportData = async (format: 'json' | 'csv') => {
    try {
      const blob = await apiClient.settings.exportData(format);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `events-export-${new Date().toISOString().split('T')[0]}.${format}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      toast.success(`Data exported as ${format.toUpperCase()}`);
    } catch (error) {
      console.error('Export failed:', error);
      toast.error('Failed to export data');
    }
  };

  const handleDeleteAllData = () => {
    const eventCount = storageStats?.total_events || 0;
    setConfirmDialog({
      open: true,
      title: 'Delete All Data?',
      description: `This will permanently delete all ${eventCount} events and thumbnails. This action cannot be undone.`,
      onConfirm: async () => {
        try {
          await apiClient.settings.deleteAllData();
          setConfirmDialog({ ...confirmDialog, open: false });
          toast.success('All data deleted successfully');
          loadStorageStats(); // Refresh stats
        } catch (error) {
          console.error('Delete failed:', error);
          toast.error('Failed to delete data');
        }
      },
      variant: 'destructive',
      requireCheckbox: true,
    });
  };

  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </div>
    );
  }

  return (
    <TooltipProvider>
      <div className="container mx-auto px-4 py-8">
        <div className="mb-6">
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Settings className="h-8 w-8" />
            System Settings
          </h1>
          <p className="text-muted-foreground mt-2">
            Configure system options and preferences
          </p>
        </div>

        <form onSubmit={form.handleSubmit(handleSave)}>
          <Tabs defaultValue="general" className="space-y-6">
            {/* Tab Navigation */}
            <TabsList className="grid w-full grid-cols-4">
              <TabsTrigger value="general" className="flex items-center gap-2">
                <Globe className="h-4 w-4" />
                <span className="hidden sm:inline">General</span>
              </TabsTrigger>
              <TabsTrigger value="ai" className="flex items-center gap-2">
                <Brain className="h-4 w-4" />
                <span className="hidden sm:inline">AI Models</span>
              </TabsTrigger>
              <TabsTrigger value="motion" className="flex items-center gap-2">
                <Eye className="h-4 w-4" />
                <span className="hidden sm:inline">Motion</span>
              </TabsTrigger>
              <TabsTrigger value="data" className="flex items-center gap-2">
                <Database className="h-4 w-4" />
                <span className="hidden sm:inline">Data</span>
              </TabsTrigger>
            </TabsList>

            {/* General Tab */}
            <TabsContent value="general" className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>General Settings</CardTitle>
                  <CardDescription>Basic system configuration</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="system-name">
                      System Name
                      <span className="text-muted-foreground ml-2 text-xs">
                        ({form.watch('system_name').length}/100)
                      </span>
                    </Label>
                    <Input
                      id="system-name"
                      {...form.register('system_name')}
                      maxLength={100}
                      placeholder="Live Object AI Classifier"
                    />
                    {form.formState.errors.system_name && (
                      <p className="text-sm text-destructive">
                        {form.formState.errors.system_name.message}
                      </p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="timezone">Timezone</Label>
                    <Select
                      value={form.watch('timezone')}
                      onValueChange={(value) => form.setValue('timezone', value, { shouldDirty: true })}
                    >
                      <SelectTrigger id="timezone">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="America/New_York">America/New_York (Eastern)</SelectItem>
                        <SelectItem value="America/Chicago">America/Chicago (Central)</SelectItem>
                        <SelectItem value="America/Denver">America/Denver (Mountain)</SelectItem>
                        <SelectItem value="America/Los_Angeles">America/Los_Angeles (Pacific)</SelectItem>
                        <SelectItem value="Europe/London">Europe/London (GMT)</SelectItem>
                        <SelectItem value="Europe/Paris">Europe/Paris (CET)</SelectItem>
                        <SelectItem value="Asia/Tokyo">Asia/Tokyo (JST)</SelectItem>
                        <SelectItem value="Australia/Sydney">Australia/Sydney (AEST)</SelectItem>
                        <SelectItem value="UTC">UTC</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="language">Language</Label>
                    <Select
                      value={form.watch('language')}
                      onValueChange={(value) => form.setValue('language', value, { shouldDirty: true })}
                    >
                      <SelectTrigger id="language">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="English">English</SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">Additional languages coming soon</p>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="date-format">Date Format</Label>
                      <Select
                        value={form.watch('date_format')}
                        onValueChange={(value) =>
                          form.setValue('date_format', value as 'MM/DD/YYYY' | 'DD/MM/YYYY' | 'YYYY-MM-DD', {
                            shouldDirty: true,
                          })
                        }
                      >
                        <SelectTrigger id="date-format">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="MM/DD/YYYY">MM/DD/YYYY</SelectItem>
                          <SelectItem value="DD/MM/YYYY">DD/MM/YYYY</SelectItem>
                          <SelectItem value="YYYY-MM-DD">YYYY-MM-DD</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2">
                      <Label>Time Format</Label>
                      <div className="flex gap-4">
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="radio"
                            value="12h"
                            checked={form.watch('time_format') === '12h'}
                            onChange={() => form.setValue('time_format', '12h', { shouldDirty: true })}
                            className="h-4 w-4"
                          />
                          <span className="text-sm">12-hour (AM/PM)</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="radio"
                            value="24h"
                            checked={form.watch('time_format') === '24h'}
                            onChange={() => form.setValue('time_format', '24h', { shouldDirty: true })}
                            className="h-4 w-4"
                          />
                          <span className="text-sm">24-hour</span>
                        </label>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            {/* AI Models Tab */}
            <TabsContent value="ai" className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>AI Provider Configuration</CardTitle>
                  <CardDescription>Configure AI models and API keys</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="primary-model">Primary Model</Label>
                    <Select
                      value={form.watch('primary_model')}
                      onValueChange={(value) =>
                        // eslint-disable-next-line @typescript-eslint/no-explicit-any
                        form.setValue('primary_model', value as any, { shouldDirty: true })
                      }
                    >
                      <SelectTrigger id="primary-model">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="gpt-4o-mini">GPT-4o mini (OpenAI)</SelectItem>
                        <SelectItem value="claude-3-haiku">Claude 3 Haiku (Anthropic)</SelectItem>
                        <SelectItem value="gemini-flash">Gemini Flash (Google)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="api-key">API Key</Label>
                    <div className="flex gap-2">
                      <div className="relative flex-1">
                        <Input
                          id="api-key"
                          type={showApiKey ? 'text' : 'password'}
                          {...form.register('primary_api_key')}
                          placeholder={form.watch('primary_api_key') ? '••••••••' : 'Enter API key'}
                        />
                      </div>
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        onClick={() => setShowApiKey(!showApiKey)}
                      >
                        {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={handleTestApiKey}
                        disabled={isTestingKey || !form.watch('primary_api_key')}
                      >
                        {isTestingKey && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                        {keyTestResult?.valid && <CheckCircle2 className="h-4 w-4 mr-2 text-green-600" />}
                        {keyTestResult?.valid === false && <XCircle className="h-4 w-4 mr-2 text-destructive" />}
                        Test
                      </Button>
                    </div>
                    {keyTestResult && !keyTestResult.valid && (
                      <p className="text-sm text-destructive">{keyTestResult.error}</p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="fallback-model">Fallback Model</Label>
                    <Select
                      value={form.watch('fallback_model') || 'none'}
                      onValueChange={(value) =>
                        // eslint-disable-next-line @typescript-eslint/no-explicit-any
                        form.setValue('fallback_model', value === 'none' ? null : (value as any), {
                          shouldDirty: true,
                        })
                      }
                    >
                      <SelectTrigger id="fallback-model">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">None</SelectItem>
                        <SelectItem value="gpt-4o-mini">GPT-4o mini (OpenAI)</SelectItem>
                        <SelectItem value="claude-3-haiku">Claude 3 Haiku (Anthropic)</SelectItem>
                        <SelectItem value="gemini-flash">Gemini Flash (Google)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="description-prompt">Description Prompt</Label>
                      <Button type="button" variant="outline" size="sm" onClick={handleResetPrompt}>
                        <RotateCcw className="h-3 w-3 mr-1" />
                        Reset to Default
                      </Button>
                    </div>
                    <Textarea
                      id="description-prompt"
                      {...form.register('description_prompt')}
                      rows={4}
                      placeholder="Enter custom AI description prompt"
                    />
                    <p className="text-xs text-muted-foreground">
                      This prompt guides the AI in generating event descriptions
                    </p>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Motion Detection Tab */}
            <TabsContent value="motion" className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Motion Detection Settings</CardTitle>
                  <CardDescription>Configure detection algorithm parameters</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <Label>Current Settings Summary</Label>
                    </div>
                    <div className="grid grid-cols-2 gap-4 p-4 bg-muted rounded-lg text-sm">
                      <div>
                        <span className="text-muted-foreground">Sensitivity:</span>{' '}
                        <span className="font-medium">{form.watch('motion_sensitivity')}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Method:</span>{' '}
                        <span className="font-medium">
                          {form.watch('detection_method') === 'background_subtraction'
                            ? 'Background Subtraction'
                            : 'Frame Difference'}
                        </span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Cooldown:</span>{' '}
                        <span className="font-medium">{form.watch('cooldown_period')}s</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Min Area:</span>{' '}
                        <span className="font-medium">{form.watch('min_motion_area')}%</span>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label>Sensitivity</Label>
                    <div className="flex items-center gap-4">
                      <span className="text-xs text-muted-foreground w-12">Low</span>
                      <Slider
                        value={[form.watch('motion_sensitivity')]}
                        onValueChange={([value]) =>
                          form.setValue('motion_sensitivity', value, { shouldDirty: true })
                        }
                        min={0}
                        max={100}
                        step={1}
                        className="flex-1"
                      />
                      <span className="text-xs text-muted-foreground w-12 text-right">High</span>
                    </div>
                    <div className="flex justify-between text-xs text-muted-foreground px-12">
                      <span>0</span>
                      <span>50 (Medium)</span>
                      <span>100</span>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label>Detection Method</Label>
                    <div className="flex flex-col gap-3">
                      <label className="flex items-start gap-3 cursor-pointer p-3 rounded-lg border hover:bg-accent">
                        <input
                          type="radio"
                          value="background_subtraction"
                          checked={form.watch('detection_method') === 'background_subtraction'}
                          onChange={() =>
                            form.setValue('detection_method', 'background_subtraction', { shouldDirty: true })
                          }
                          className="mt-0.5 h-4 w-4"
                        />
                        <div className="flex-1">
                          <div className="font-medium text-sm">Background Subtraction</div>
                          <div className="text-xs text-muted-foreground">
                            Learns background over time, better for stationary cameras
                          </div>
                        </div>
                      </label>
                      <label className="flex items-start gap-3 cursor-pointer p-3 rounded-lg border hover:bg-accent">
                        <input
                          type="radio"
                          value="frame_difference"
                          checked={form.watch('detection_method') === 'frame_difference'}
                          onChange={() =>
                            form.setValue('detection_method', 'frame_difference', { shouldDirty: true })
                          }
                          className="mt-0.5 h-4 w-4"
                        />
                        <div className="flex-1">
                          <div className="font-medium text-sm">Frame Difference</div>
                          <div className="text-xs text-muted-foreground">
                            Compares consecutive frames, better for changing scenes
                          </div>
                        </div>
                      </label>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="cooldown">
                        Cooldown Period (seconds)
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="ml-1 text-muted-foreground cursor-help">ⓘ</span>
                          </TooltipTrigger>
                          <TooltipContent>
                            <p>Minimum time between motion detections</p>
                          </TooltipContent>
                        </Tooltip>
                      </Label>
                      <Input
                        id="cooldown"
                        type="number"
                        min={30}
                        max={300}
                        {...form.register('cooldown_period', { valueAsNumber: true })}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label>Min Motion Area (%)</Label>
                      <Slider
                        value={[form.watch('min_motion_area')]}
                        onValueChange={([value]) =>
                          form.setValue('min_motion_area', value, { shouldDirty: true })
                        }
                        min={1}
                        max={10}
                        step={0.5}
                      />
                      <p className="text-xs text-muted-foreground">
                        Current: {form.watch('min_motion_area')}% of frame size
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center justify-between p-3 rounded-lg border">
                    <div className="flex-1">
                      <Label htmlFor="debug-images" className="cursor-pointer">
                        Save Debug Images
                      </Label>
                      <p className="text-xs text-muted-foreground">
                        Store debug images for troubleshooting
                      </p>
                    </div>
                    <Switch
                      id="debug-images"
                      checked={form.watch('save_debug_images')}
                      onCheckedChange={(checked) =>
                        form.setValue('save_debug_images', checked, { shouldDirty: true })
                      }
                    />
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Data & Privacy Tab */}
            <TabsContent value="data" className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Data & Privacy</CardTitle>
                  <CardDescription>Manage data retention and storage</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {storageStats && (
                    <div className="p-4 rounded-lg border bg-muted/50">
                      <h4 className="font-medium mb-3">Storage Statistics</h4>
                      <div className="grid grid-cols-2 gap-3 text-sm">
                        <div>
                          <span className="text-muted-foreground">Total Events:</span>{' '}
                          <span className="font-medium">{(storageStats.total_events ?? 0).toLocaleString()}</span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Database:</span>{' '}
                          <span className="font-medium">{(storageStats.database_mb ?? 0).toFixed(1)} MB</span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Thumbnails:</span>{' '}
                          <span className="font-medium">{(storageStats.thumbnails_mb ?? 0).toFixed(1)} MB</span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Total:</span>{' '}
                          <span className="font-medium">{(storageStats.total_mb ?? 0).toFixed(1)} MB</span>
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="space-y-2">
                    <Label htmlFor="retention">Data Retention</Label>
                    <Select
                      value={String(form.watch('retention_days'))}
                      onValueChange={(value) =>
                        form.setValue('retention_days', parseInt(value), { shouldDirty: true })
                      }
                    >
                      <SelectTrigger id="retention">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="7">7 days</SelectItem>
                        <SelectItem value="30">30 days</SelectItem>
                        <SelectItem value="90">90 days</SelectItem>
                        <SelectItem value="365">1 year</SelectItem>
                        <SelectItem value="-1">Forever</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label>Thumbnail Storage</Label>
                    <div className="flex flex-col gap-3">
                      <label className="flex items-start gap-3 cursor-pointer p-3 rounded-lg border hover:bg-accent">
                        <input
                          type="radio"
                          value="filesystem"
                          checked={form.watch('thumbnail_storage') === 'filesystem'}
                          onChange={() =>
                            form.setValue('thumbnail_storage', 'filesystem', { shouldDirty: true })
                          }
                          className="mt-0.5 h-4 w-4"
                        />
                        <div className="flex-1">
                          <div className="font-medium text-sm">File System</div>
                          <div className="text-xs text-muted-foreground">Store thumbnails as files (faster)</div>
                        </div>
                      </label>
                      <label className="flex items-start gap-3 cursor-pointer p-3 rounded-lg border hover:bg-accent">
                        <input
                          type="radio"
                          value="database"
                          checked={form.watch('thumbnail_storage') === 'database'}
                          onChange={() =>
                            form.setValue('thumbnail_storage', 'database', { shouldDirty: true })
                          }
                          className="mt-0.5 h-4 w-4"
                        />
                        <div className="flex-1">
                          <div className="font-medium text-sm">Database</div>
                          <div className="text-xs text-muted-foreground">Store in database (portable)</div>
                        </div>
                      </label>
                    </div>
                  </div>

                  <div className="flex items-center justify-between p-3 rounded-lg border">
                    <div className="flex-1">
                      <Label htmlFor="auto-cleanup" className="cursor-pointer">
                        Auto Cleanup
                      </Label>
                      <p className="text-xs text-muted-foreground">
                        Automatically delete old events based on retention policy
                      </p>
                    </div>
                    <Switch
                      id="auto-cleanup"
                      checked={form.watch('auto_cleanup')}
                      onCheckedChange={(checked) =>
                        form.setValue('auto_cleanup', checked, { shouldDirty: true })
                      }
                    />
                  </div>

                  <div className="space-y-3 pt-4 border-t">
                    <h4 className="font-medium">Data Management</h4>
                    <div className="flex flex-col sm:flex-row gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => handleExportData('json')}
                        className="flex-1"
                      >
                        <Download className="h-4 w-4 mr-2" />
                        Export JSON
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => handleExportData('csv')}
                        className="flex-1"
                      >
                        <Download className="h-4 w-4 mr-2" />
                        Export CSV
                      </Button>
                    </div>
                    <Button
                      type="button"
                      variant="destructive"
                      onClick={handleDeleteAllData}
                      className="w-full"
                    >
                      <Trash2 className="h-4 w-4 mr-2" />
                      Delete All Data
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {/* Backup & Restore Section (Story 6.4) */}
              <BackupRestore />
            </TabsContent>
          </Tabs>

          {/* Footer Actions */}
          <div className="flex justify-between items-center pt-6 border-t">
            <Button type="button" variant="outline" onClick={handleCancel} disabled={!isDirty || isSaving}>
              Cancel
            </Button>
            <Button type="submit" disabled={!isDirty || isSaving}>
              {isSaving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Save Changes
            </Button>
          </div>
        </form>

        {/* Confirmation Dialog */}
        <ConfirmDialog {...confirmDialog} onOpenChange={(open) => setConfirmDialog({ ...confirmDialog, open })} />
      </div>
    </TooltipProvider>
  );
}
