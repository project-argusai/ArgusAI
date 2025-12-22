/**
 * System Settings Page
 * Centralized settings management with tabbed interface
 * Story 4.4: Build System Settings Page
 * Story P2-6.3: Error handling with ErrorBoundary (AC17)
 */

'use client';

import { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
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
  Download,
  Trash2,
  Shield,
  FileText,
  DollarSign,
  Bell,
  Network,
  BarChart3,
  Sparkles,
} from 'lucide-react';

import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { ConnectionErrorBanner, getConnectionErrorType } from '@/components/protect/ConnectionErrorBanner';

import { apiClient } from '@/lib/api-client';
import { completeSettingsSchema } from '@/lib/settings-validation';
import { useSettings } from '@/contexts/SettingsContext';
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
import { AIProviders } from '@/components/settings/AIProviders';
import { LogViewer } from '@/components/settings/LogViewer';
import { CostDashboard } from '@/components/settings/CostDashboard';
import { AccuracyDashboard } from '@/components/settings/AccuracyDashboard';
import { PushNotificationSettings } from '@/components/settings/PushNotificationSettings';
import { MQTTSettings } from '@/components/settings/MQTTSettings';
import { HomekitSettings } from '@/components/settings/HomekitSettings';
import { AnomalySettings } from '@/components/settings/AnomalySettings';
import { MotionEventsExport } from '@/components/settings/MotionEventsExport';
import { PromptRefinementModal } from '@/components/settings/PromptRefinementModal';
import { CostWarningModal } from '@/components/settings/CostWarningModal';
import { VideoStorageWarningModal } from '@/components/settings/VideoStorageWarningModal';
import { FrameSamplingStrategySelector, type FrameSamplingStrategy } from '@/components/settings/FrameSamplingStrategySelector';
import { ControllerForm, type ControllerData, DeleteControllerDialog, DiscoveredCameraList } from '@/components/protect';
import { useQuery } from '@tanstack/react-query';
import type { AIProvider } from '@/types/settings';


export default function SettingsPage() {
  const searchParams = useSearchParams();
  const initialTab = searchParams.get('tab') || 'general';
  const { refreshSystemName } = useSettings(); // BUG-003: Refresh system name after save

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
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

  // AI Providers state - track which providers have API keys configured
  const [configuredProviders, setConfiguredProviders] = useState<Set<AIProvider>>(new Set());
  const [providerOrder, setProviderOrder] = useState<AIProvider[]>(['openai', 'grok', 'anthropic', 'google']);

  // UniFi Protect controller state
  const [showControllerForm, setShowControllerForm] = useState(false);
  const [editingController, setEditingController] = useState<ControllerData | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  // Story P8-2.3: Frame count setting state
  const [costWarningOpen, setCostWarningOpen] = useState(false);
  const [pendingFrameCount, setPendingFrameCount] = useState<5 | 10 | 15 | 20 | null>(null);

  // Story P8-3.2: Video storage setting state
  const [videoStorageWarningOpen, setVideoStorageWarningOpen] = useState(false);

  // Story P8-3.3: Prompt refinement modal state
  const [promptRefinementOpen, setPromptRefinementOpen] = useState(false);

  // Query for existing Protect controllers
  const controllersQuery = useQuery({
    queryKey: ['protect-controllers'],
    queryFn: () => apiClient.protect.listControllers(),
  });

  const hasController = (controllersQuery.data?.length ?? 0) > 0;
  const controller = controllersQuery.data?.[0];

  const form = useForm<SystemSettings>({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    resolver: zodResolver(completeSettingsSchema) as any,
    defaultValues: {
      system_name: 'ArgusAI',
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      language: 'English',
      date_format: 'MM/DD/YYYY',
      time_format: '12h',
      description_prompt: 'Describe what you see in this image in one concise sentence. Focus on objects, people, and actions.',
      motion_sensitivity: 50,
      detection_method: 'background_subtraction',
      cooldown_period: 60,
      min_motion_area: 5,
      save_debug_images: false,
      retention_days: 30,
      thumbnail_storage: 'filesystem',
      auto_cleanup: true,
      analysis_frame_count: 10, // Story P8-2.3: Default frame count
      frame_sampling_strategy: 'uniform', // Story P8-2.5: Default sampling strategy
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
    loadAIProvidersStatus();
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
      const stats = await apiClient.settings.storage();
      setStorageStats(stats);
    } catch (error) {
      console.error('Failed to load storage stats:', error);
    }
  };

  const loadAIProvidersStatus = async () => {
    try {
      const response = await apiClient.settings.getAIProvidersStatus();
      // Convert provider status to Set of configured providers
      const configured = new Set<AIProvider>(
        response.providers
          .filter(p => p.configured)
          .map(p => p.provider as AIProvider)
      );
      setConfiguredProviders(configured);
      // Update provider order if returned
      if (response.order && response.order.length > 0) {
        setProviderOrder(response.order as AIProvider[]);
      }
    } catch (error) {
      console.error('Failed to load AI providers status:', error);
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
      // BUG-003: Refresh system name in context if it was changed
      if ('system_name' in changedData) {
        await refreshSystemName();
      }
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

  const handleExportData = async (format: 'json' | 'csv') => {
    // TODO: Implement data export API endpoint
    toast.error(`Data export not yet implemented`);
    console.log('Export format requested:', format);
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
          <Tabs defaultValue={initialTab} className="space-y-6">
            {/* Tab Navigation - horizontal scrollable row */}
            <div className="overflow-x-auto border-b pb-2">
              <TabsList style={{ display: 'inline-flex', flexDirection: 'row', flexWrap: 'nowrap', width: 'max-content' }} className="h-10 items-center gap-1 rounded-lg bg-muted p-1">
                <TabsTrigger value="general" className="flex items-center gap-2 px-3">
                  <Globe className="h-4 w-4" />
                  <span className="hidden sm:inline">General</span>
                </TabsTrigger>
                <TabsTrigger value="ai" className="flex items-center gap-2 px-3">
                  <Brain className="h-4 w-4" />
                  <span className="hidden sm:inline">AI Models</span>
                </TabsTrigger>
                <TabsTrigger value="ai-usage" className="flex items-center gap-2 px-3">
                  <DollarSign className="h-4 w-4" />
                  <span className="hidden sm:inline">AI Usage</span>
                </TabsTrigger>
                <TabsTrigger value="motion" className="flex items-center gap-2 px-3">
                  <Eye className="h-4 w-4" />
                  <span className="hidden sm:inline">Motion</span>
                </TabsTrigger>
                <TabsTrigger value="data" className="flex items-center gap-2 px-3">
                  <Database className="h-4 w-4" />
                  <span className="hidden sm:inline">Data</span>
                </TabsTrigger>
                <TabsTrigger value="protect" className="flex items-center gap-2 px-3">
                  <Shield className="h-4 w-4" />
                  <span className="hidden sm:inline">Protect</span>
                </TabsTrigger>
                <TabsTrigger value="integrations" className="flex items-center gap-2 px-3">
                  <Network className="h-4 w-4" />
                  <span className="hidden sm:inline">Integrations</span>
                </TabsTrigger>
                <TabsTrigger value="notifications" className="flex items-center gap-2 px-3">
                  <Bell className="h-4 w-4" />
                  <span className="hidden sm:inline">Notifications</span>
                </TabsTrigger>
                <TabsTrigger value="logs" className="flex items-center gap-2 px-3">
                  <FileText className="h-4 w-4" />
                  <span className="hidden sm:inline">Logs</span>
                </TabsTrigger>
                <TabsTrigger value="accuracy" className="flex items-center gap-2 px-3">
                  <BarChart3 className="h-4 w-4" />
                  <span className="hidden sm:inline">AI Accuracy</span>
                </TabsTrigger>
              </TabsList>
            </div>

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
                      placeholder="ArgusAI"
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

                  {/* Story P8-2.3: Analysis Frame Count Setting */}
                  <div className="space-y-2 pt-4 border-t">
                    <Label htmlFor="analysis-frame-count">Analysis Frame Count</Label>
                    <Select
                      value={String(form.watch('analysis_frame_count') || 10)}
                      onValueChange={(value) => {
                        const newValue = parseInt(value, 10) as 5 | 10 | 15 | 20;
                        // Show cost warning modal before applying change
                        setPendingFrameCount(newValue);
                        setCostWarningOpen(true);
                      }}
                    >
                      <SelectTrigger id="analysis-frame-count">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="5">5 frames (fastest, lowest cost)</SelectItem>
                        <SelectItem value="10">10 frames (default, balanced)</SelectItem>
                        <SelectItem value="15">15 frames (higher accuracy)</SelectItem>
                        <SelectItem value="20">20 frames (highest accuracy, highest cost)</SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      Number of video frames extracted for AI analysis. More frames may improve description accuracy but increase AI costs.
                    </p>
                  </div>

                  {/* Story P8-2.5: Frame Sampling Strategy Selector */}
                  <div className="pt-4 border-t">
                    <FrameSamplingStrategySelector
                      value={(form.watch('frame_sampling_strategy') || 'uniform') as FrameSamplingStrategy}
                      onChange={async (value) => {
                        try {
                          // Save immediately to backend
                          await apiClient.settings.update({ frame_sampling_strategy: value });
                          form.setValue('frame_sampling_strategy', value, { shouldDirty: false });
                          toast.success(`Frame sampling strategy updated to ${value}`);
                        } catch (error) {
                          console.error('Failed to save sampling strategy:', error);
                          toast.error('Failed to save sampling strategy setting');
                        }
                      }}
                    />
                  </div>

                  {/* Story P8-3.2: Video Storage Settings */}
                  <div className="space-y-4 pt-4 border-t">
                    <div className="flex items-center justify-between">
                      <div className="space-y-0.5">
                        <Label htmlFor="store-motion-videos">Store Motion Videos</Label>
                        <p className="text-xs text-muted-foreground">
                          Download and store full motion clips from Protect cameras for complete video review.
                        </p>
                      </div>
                      <Switch
                        id="store-motion-videos"
                        checked={form.watch('store_motion_videos') || false}
                        onCheckedChange={(checked) => {
                          if (checked) {
                            // Show warning before enabling
                            setVideoStorageWarningOpen(true);
                          } else {
                            // Disable immediately
                            apiClient.settings.update({ store_motion_videos: false })
                              .then(() => {
                                form.setValue('store_motion_videos', false, { shouldDirty: false });
                                toast.success('Video storage disabled');
                              })
                              .catch((error) => {
                                console.error('Failed to save video storage setting:', error);
                                toast.error('Failed to save setting');
                              });
                          }
                        }}
                      />
                    </div>

                    {form.watch('store_motion_videos') && (
                      <div className="space-y-2 pl-4 border-l-2 border-muted">
                        <Label htmlFor="video-retention-days">Video Retention (Days)</Label>
                        <Select
                          value={String(form.watch('video_retention_days') || 30)}
                          onValueChange={async (value) => {
                            const days = parseInt(value, 10);
                            try {
                              await apiClient.settings.update({ video_retention_days: days });
                              form.setValue('video_retention_days', days, { shouldDirty: false });
                              toast.success(`Video retention set to ${days} days`);
                            } catch (error) {
                              console.error('Failed to save video retention:', error);
                              toast.error('Failed to save video retention setting');
                            }
                          }}
                        >
                          <SelectTrigger id="video-retention-days" className="w-48">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="7">7 days</SelectItem>
                            <SelectItem value="14">14 days</SelectItem>
                            <SelectItem value="30">30 days (default)</SelectItem>
                            <SelectItem value="60">60 days</SelectItem>
                            <SelectItem value="90">90 days</SelectItem>
                            <SelectItem value="180">180 days</SelectItem>
                            <SelectItem value="365">365 days</SelectItem>
                          </SelectContent>
                        </Select>
                        <p className="text-xs text-muted-foreground">
                          Videos older than this will be automatically deleted. This is separate from event retention.
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Story P9-3.2: OCR Frame Overlay Extraction */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="space-y-0.5">
                        <Label htmlFor="attempt-ocr-extraction" className="text-sm font-medium">
                          OCR Frame Overlay Extraction
                        </Label>
                        <p className="text-xs text-muted-foreground">
                          Attempt to extract timestamp and camera name from video frame overlays using OCR.
                        </p>
                      </div>
                      <Switch
                        id="attempt-ocr-extraction"
                        checked={form.watch('attempt_ocr_extraction') || false}
                        onCheckedChange={async (checked) => {
                          try {
                            await apiClient.settings.update({ attempt_ocr_extraction: checked });
                            form.setValue('attempt_ocr_extraction', checked, { shouldDirty: false });
                            toast.success(checked ? 'OCR extraction enabled' : 'OCR extraction disabled');
                          } catch (error) {
                            console.error('Failed to save OCR setting:', error);
                            toast.error('Failed to save setting');
                          }
                        }}
                      />
                    </div>
                    {form.watch('attempt_ocr_extraction') && (
                      <div className="p-3 rounded-md bg-muted/50 border">
                        <p className="text-xs text-muted-foreground">
                          <strong>Note:</strong> OCR extraction is CPU-intensive and requires Tesseract to be installed
                          on the server. This feature attempts to read embedded timestamps and camera names from
                          security camera overlays, supplementing database metadata for more accurate context.
                        </p>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Story P8-2.3: Cost Warning Modal */}
              <CostWarningModal
                open={costWarningOpen}
                onOpenChange={setCostWarningOpen}
                newValue={pendingFrameCount || 10}
                onConfirm={async () => {
                  if (pendingFrameCount) {
                    try {
                      // Save immediately to backend
                      await apiClient.settings.update({ analysis_frame_count: pendingFrameCount });
                      form.setValue('analysis_frame_count', pendingFrameCount, { shouldDirty: false });
                      toast.success(`Frame count updated to ${pendingFrameCount}`);
                    } catch (error) {
                      console.error('Failed to save frame count:', error);
                      toast.error('Failed to save frame count setting');
                    }
                  }
                  setPendingFrameCount(null);
                }}
                onCancel={() => {
                  setPendingFrameCount(null);
                }}
              />

              {/* Story P8-3.2: Video Storage Warning Modal */}
              <VideoStorageWarningModal
                open={videoStorageWarningOpen}
                onOpenChange={setVideoStorageWarningOpen}
                onConfirm={async () => {
                  try {
                    await apiClient.settings.update({ store_motion_videos: true });
                    form.setValue('store_motion_videos', true, { shouldDirty: false });
                    toast.success('Video storage enabled');
                  } catch (error) {
                    console.error('Failed to enable video storage:', error);
                    toast.error('Failed to enable video storage');
                  }
                }}
                onCancel={() => {
                  // Don't change the setting
                }}
              />
            </TabsContent>

            {/* AI Models Tab */}
            <TabsContent value="ai" className="space-y-4">
              {/* AI Providers List - Story P2-5.2, wrapped with ErrorBoundary (P2-6.3 AC17) */}
              <ErrorBoundary context="AI Providers">
                <AIProviders
                  configuredProviders={configuredProviders}
                  providerOrder={providerOrder}
                  onProviderConfigured={(provider) => {
                    setConfiguredProviders((prev) => new Set([...prev, provider]));
                  }}
                  onProviderRemoved={(provider) => {
                    setConfiguredProviders((prev) => {
                      const next = new Set(prev);
                      next.delete(provider);
                      return next;
                    });
                  }}
                  onProviderOrderChanged={(order) => {
                    setProviderOrder(order);
                  }}
                />
              </ErrorBoundary>

              {/* Description Prompt Card */}
              <Card>
                <CardHeader>
                  <CardTitle>AI Description Prompt</CardTitle>
                  <CardDescription>Customize how the AI describes detected events</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="description-prompt">Prompt Template</Label>
                      <div className="flex gap-2">
                        {/* Story P8-3.3: AI-Assisted Prompt Refinement Button */}
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => setPromptRefinementOpen(true)}
                        >
                          <Sparkles className="h-4 w-4 mr-2" />
                          Refine with AI
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            form.setValue('description_prompt', 'Describe what you see in this image in one concise sentence. Focus on objects, people, and actions.', { shouldDirty: true });
                            toast.success('Prompt reset to default');
                          }}
                        >
                          Reset to Default
                        </Button>
                      </div>
                    </div>
                    <Textarea
                      id="description-prompt"
                      {...form.register('description_prompt')}
                      rows={4}
                      placeholder="Enter custom AI description prompt"
                    />
                    <p className="text-xs text-muted-foreground">
                      This prompt guides the AI in generating event descriptions. A good prompt should ask for concise, relevant details about what&apos;s happening in the image.
                    </p>
                  </div>
                </CardContent>
              </Card>

              {/* Story P9-3.5: Summary Prompt Customization */}
              <Card>
                <CardHeader>
                  <CardTitle>Summary Prompt</CardTitle>
                  <CardDescription>Customize the prompt used for generating activity summaries</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="summary-prompt">Summary Prompt Template</Label>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          const defaultPrompt = `Generate a daily activity summary for {date}.
Summarize the {event_count} events detected across {camera_count} cameras.
Highlight any notable patterns or unusual activity.
Keep the summary concise (2-3 paragraphs).`;
                          form.setValue('summary_prompt', defaultPrompt, { shouldDirty: true });
                          toast.success('Summary prompt reset to default');
                        }}
                      >
                        Reset to Default
                      </Button>
                    </div>
                    <Textarea
                      id="summary-prompt"
                      {...form.register('summary_prompt')}
                      rows={5}
                      placeholder="Enter custom summary generation prompt"
                      maxLength={2000}
                      defaultValue={`Generate a daily activity summary for {date}.
Summarize the {event_count} events detected across {camera_count} cameras.
Highlight any notable patterns or unusual activity.
Keep the summary concise (2-3 paragraphs).`}
                    />
                    <div className="flex items-center justify-between">
                      <p className="text-xs text-muted-foreground">
                        Available variables: <code className="bg-muted px-1 rounded">{'{date}'}</code>, <code className="bg-muted px-1 rounded">{'{event_count}'}</code>, <code className="bg-muted px-1 rounded">{'{camera_count}'}</code>
                      </p>
                      <span className="text-xs text-muted-foreground">
                        {(form.watch('summary_prompt') || '').length}/2000
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Story P8-3.3: Prompt Refinement Modal */}
              <PromptRefinementModal
                open={promptRefinementOpen}
                onOpenChange={setPromptRefinementOpen}
                currentPrompt={form.watch('description_prompt') || ''}
                onAccept={(newPrompt) => {
                  form.setValue('description_prompt', newPrompt, { shouldDirty: true });
                }}
              />
            </TabsContent>

            {/* AI Usage Tab - Story P3-7.2 */}
            <TabsContent value="ai-usage" className="space-y-4">
              <ErrorBoundary context="AI Usage Dashboard">
                <CostDashboard />
              </ErrorBoundary>
            </TabsContent>

            {/* Motion Detection Tab */}
            <TabsContent value="motion" className="space-y-4">
              {/* Story P4-7.3: Anomaly Detection Settings */}
              <ErrorBoundary context="Anomaly Settings">
                <AnomalySettings />
              </ErrorBoundary>

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

              {/* Motion Events Export Section (Story P6-4.2) */}
              <MotionEventsExport />

              {/* Backup & Restore Section (Story 6.4) */}
              <BackupRestore />
            </TabsContent>

            {/* UniFi Protect Tab (Story P2-1.3) */}
            <TabsContent value="protect" className="space-y-4">
              <Card>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <Shield className="h-5 w-5 text-cyan-500" />
                    <CardTitle>UniFi Protect Integration</CardTitle>
                  </div>
                  <CardDescription>
                    Connect your UniFi Protect controller to auto-discover cameras and receive motion events
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {controllersQuery.isLoading ? (
                    <div className="flex items-center justify-center py-8">
                      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                  ) : hasController && !showControllerForm ? (
                    /* Controller Configured View */
                    <div className="space-y-4">
                      <div className="p-4 rounded-lg border bg-muted/50">
                        <div className="flex items-center justify-between">
                          <div>
                            <h4 className="font-medium">{controller?.name}</h4>
                            <p className="text-sm text-muted-foreground">
                              {controller?.host}:{controller?.port}
                            </p>
                          </div>
                          <div className="flex items-center gap-2">
                            <span
                              className={`h-3 w-3 rounded-full ${
                                controller?.is_connected ? 'bg-green-500' : 'bg-gray-400'
                              }`}
                            />
                            <span className="text-sm text-muted-foreground">
                              {controller?.is_connected ? 'Connected' : 'Not connected'}
                            </span>
                          </div>
                        </div>
                      </div>
                      {/* Story P2-6.3 AC1-4: Connection error banner */}
                      {controller && !controller.is_connected && (
                        <ConnectionErrorBanner
                          errorType={getConnectionErrorType(undefined, controller.last_error ?? undefined)}
                          errorMessage={controller.last_error ?? 'Controller is not connected'}
                          onRetry={() => controllersQuery.refetch()}
                          onEditCredentials={() => {
                            setEditingController(controller as unknown as ControllerData);
                            setShowControllerForm(true);
                          }}
                          className="mt-3"
                        />
                      )}
                      {/* Edit and Remove buttons (Story P2-1.5) */}
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          onClick={() => {
                            setEditingController(controller as unknown as ControllerData);
                            setShowControllerForm(true);
                          }}
                        >
                          Edit
                        </Button>
                        <Button
                          variant="destructive"
                          onClick={() => setDeleteDialogOpen(true)}
                        >
                          <Trash2 className="h-4 w-4 mr-2" />
                          Remove
                        </Button>
                      </div>

                      {/* Discovered Cameras List (Story P2-2.2), wrapped with ErrorBoundary (P2-6.3 AC17) */}
                      {controller && (
                        <ErrorBoundary context="Discovered Cameras">
                          <DiscoveredCameraList
                            controllerId={String(controller.id)}
                            isControllerConnected={controller.is_connected}
                          />
                        </ErrorBoundary>
                      )}
                    </div>
                  ) : showControllerForm ? (
                    /* Controller Form */
                    <div className="sm:grid sm:grid-cols-2 sm:gap-6">
                      <div className="col-span-1">
                        <ControllerForm
                          controller={editingController ?? undefined}
                          onSaveSuccess={() => {
                            setShowControllerForm(false);
                            setEditingController(null);
                            controllersQuery.refetch();
                          }}
                          onCancel={() => {
                            setShowControllerForm(false);
                            setEditingController(null);
                          }}
                        />
                      </div>
                      <div className="hidden sm:block col-span-1">
                        <Card className="h-full">
                          <CardHeader>
                            <CardTitle className="text-lg">About UniFi Protect</CardTitle>
                          </CardHeader>
                          <CardContent className="text-sm text-muted-foreground space-y-3">
                            <p>
                              UniFi Protect is Ubiquiti&apos;s video surveillance platform that manages
                              cameras, doorbells, and sensors.
                            </p>
                            <p>
                              Connecting your Protect controller allows this system to:
                            </p>
                            <ul className="list-disc list-inside space-y-1">
                              <li>Auto-discover all connected cameras</li>
                              <li>Receive real-time motion events</li>
                              <li>Process doorbell ring notifications</li>
                              <li>Generate AI descriptions for events</li>
                            </ul>
                            <p className="text-xs">
                              Your credentials are encrypted and stored securely.
                            </p>
                          </CardContent>
                        </Card>
                      </div>
                    </div>
                  ) : (
                    /* Empty State */
                    <div className="text-center py-8">
                      <Shield className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                      <h3 className="text-lg font-medium mb-2">No Controller Configured</h3>
                      <p className="text-muted-foreground mb-4">
                        Connect your UniFi Protect controller to auto-discover cameras and receive events
                      </p>
                      <Button onClick={() => setShowControllerForm(true)}>
                        <Shield className="h-4 w-4 mr-2" />
                        Add Controller
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* Integrations Tab - Story P4-2.4, P4-6.1 */}
            <TabsContent value="integrations" className="space-y-4">
              <ErrorBoundary context="MQTT Settings">
                <MQTTSettings />
              </ErrorBoundary>
              <ErrorBoundary context="HomeKit Settings">
                <HomekitSettings />
              </ErrorBoundary>
            </TabsContent>

            {/* Notifications Tab - Story P4-1.2 */}
            <TabsContent value="notifications" className="space-y-4">
              <PushNotificationSettings />
            </TabsContent>

            {/* Logs Tab - FF-001 */}
            <TabsContent value="logs" className="space-y-4">
              <LogViewer />
            </TabsContent>

            {/* AI Accuracy Tab - Story P4-5.3 */}
            <TabsContent value="accuracy" className="space-y-4">
              <ErrorBoundary context="AI Accuracy Dashboard">
                <AccuracyDashboard />
              </ErrorBoundary>
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

        {/* Delete Controller Dialog (Story P2-1.5) */}
        {controller && (
          <DeleteControllerDialog
            open={deleteDialogOpen}
            onOpenChange={setDeleteDialogOpen}
            controllerId={String(controller.id)}
            controllerName={controller.name}
            onDeleteSuccess={() => {
              controllersQuery.refetch();
            }}
          />
        )}
      </div>
    </TooltipProvider>
  );
}
