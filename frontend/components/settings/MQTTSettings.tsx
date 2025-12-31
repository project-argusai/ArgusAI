/**
 * MQTT Settings Component (Story P4-2.4, P5-6.2, P8-3.1, P15-3.5)
 *
 * Features:
 * - MQTT broker configuration form (AC 2, 6, 7, 9)
 * - Connection status display with real-time polling (AC 4)
 * - Test connection button (AC 3)
 * - Save functionality with validation (AC 5, 8)
 * - Publish discovery button (AC 10)
 * - Birth/Will message configuration (P5-6.2)
 * - Conditional visibility of form fields based on enabled state (P8-3.1)
 * - Unsaved changes indicator and navigation warning (P15-3.5)
 */

'use client';

import { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Network,
  Wifi,
  WifiOff,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  Send,
  RefreshCw,
  Eye,
  EyeOff,
  Info,
  Bell,
} from 'lucide-react';

import { apiClient } from '@/lib/api-client';
import { useUnsavedChangesWarning } from '@/hooks/useUnsavedChangesWarning';
import { UnsavedIndicator } from './UnsavedIndicator';
import type { MQTTConfigUpdate } from '@/types/settings';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

// Validation schema (AC 8, P5-6.1, P5-6.2)
const mqttConfigSchema = z.object({
  broker_host: z.string().min(1, 'Broker host is required').max(255),
  broker_port: z.coerce.number().int().min(1, 'Port must be between 1-65535').max(65535, 'Port must be between 1-65535'),
  username: z.string().max(100).optional().or(z.literal('')),
  password: z.string().max(500).optional().or(z.literal('')),
  topic_prefix: z.string().min(1, 'Topic prefix is required').max(100),
  discovery_prefix: z.string().min(1, 'Discovery prefix is required').max(100),
  discovery_enabled: z.boolean(),
  qos: z.coerce.number().int().min(0).max(2),
  enabled: z.boolean(),
  retain_messages: z.boolean(),
  use_tls: z.boolean(),
  message_expiry_seconds: z.coerce.number().int().min(60, 'Expiry must be at least 60 seconds').max(3600, 'Expiry must be at most 3600 seconds'),
  availability_topic: z.string().max(255).optional().or(z.literal('')),
  birth_message: z.string().min(1, 'Birth message is required').max(100),
  will_message: z.string().min(1, 'Will message is required').max(100),
});

interface MQTTFormData {
  broker_host: string;
  broker_port: number;
  username?: string;
  password?: string;
  topic_prefix: string;
  discovery_prefix: string;
  discovery_enabled: boolean;
  qos: 0 | 1 | 2;
  enabled: boolean;
  retain_messages: boolean;
  use_tls: boolean;
  message_expiry_seconds: number;
  availability_topic: string;
  birth_message: string;
  will_message: string;
}

export function MQTTSettings() {
  const queryClient = useQueryClient();
  const [showPassword, setShowPassword] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);
  const [isSendingTestMessage, setIsSendingTestMessage] = useState(false);

  // Fetch MQTT configuration
  const configQuery = useQuery({
    queryKey: ['mqtt-config'],
    queryFn: () => apiClient.mqtt.getConfig(),
  });

  // Fetch MQTT status with polling (AC 4)
  const statusQuery = useQuery({
    queryKey: ['mqtt-status'],
    queryFn: () => apiClient.mqtt.getStatus(),
    refetchInterval: 5000, // Poll every 5 seconds
  });

  // Form setup
  const form = useForm<MQTTFormData>({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    resolver: zodResolver(mqttConfigSchema) as any,
    defaultValues: {
      broker_host: '',
      broker_port: 1883,
      username: '',
      password: '',
      topic_prefix: 'liveobject',
      discovery_prefix: 'homeassistant',
      discovery_enabled: true,
      qos: 1,
      enabled: false,
      retain_messages: true,
      use_tls: false,
      message_expiry_seconds: 300,
      availability_topic: '',
      birth_message: 'online',
      will_message: 'offline',
    },
  });

  const { formState: { errors, isDirty } } = form;

  // Navigation warning when form is dirty
  useUnsavedChangesWarning({ isDirty });

  // Update form when config loads
  useEffect(() => {
    if (configQuery.data) {
      const config = configQuery.data;
      form.reset({
        broker_host: config.broker_host || '',
        broker_port: config.broker_port,
        username: config.username || '',
        password: '', // Never prefill password
        topic_prefix: config.topic_prefix,
        discovery_prefix: config.discovery_prefix,
        discovery_enabled: config.discovery_enabled,
        qos: config.qos,
        enabled: config.enabled,
        retain_messages: config.retain_messages,
        use_tls: config.use_tls,
        message_expiry_seconds: config.message_expiry_seconds,
        availability_topic: config.availability_topic || '',
        birth_message: config.birth_message || 'online',
        will_message: config.will_message || 'offline',
      });
    }
  }, [configQuery.data, form]);

  // Save mutation (AC 5)
  const saveMutation = useMutation({
    mutationFn: (data: MQTTConfigUpdate) => apiClient.mqtt.updateConfig(data),
    onSuccess: () => {
      toast.success('MQTT configuration saved', {
        description: 'Settings updated and connection will reconnect if enabled.',
      });
      queryClient.invalidateQueries({ queryKey: ['mqtt-config'] });
      queryClient.invalidateQueries({ queryKey: ['mqtt-status'] });
    },
    onError: (error: Error) => {
      toast.error('Failed to save configuration', {
        description: error.message,
      });
    },
  });

  // Test connection handler (AC 3)
  const handleTestConnection = async () => {
    const values = form.getValues();
    if (!values.broker_host) {
      toast.error('Enter broker host first');
      return;
    }

    setIsTesting(true);
    try {
      // Use stored password if not provided and password exists
      const passwordToUse = values.password || (configQuery.data?.has_password ? undefined : '');

      const result = await apiClient.mqtt.testConnection({
        broker_host: values.broker_host,
        broker_port: values.broker_port,
        username: values.username || undefined,
        password: passwordToUse,
        use_tls: values.use_tls,
      });

      if (result.success) {
        toast.success('Connection successful', {
          description: result.message,
        });
      } else {
        toast.error('Connection failed', {
          description: result.message,
        });
      }
    } catch (error) {
      toast.error('Test failed', {
        description: error instanceof Error ? error.message : 'Unknown error',
      });
    } finally {
      setIsTesting(false);
    }
  };

  // Publish discovery handler (AC 10)
  const handlePublishDiscovery = async () => {
    setIsPublishing(true);
    try {
      const result = await apiClient.mqtt.publishDiscovery();
      if (result.success) {
        toast.success('Discovery published', {
          description: `Published ${result.cameras_published} camera${result.cameras_published !== 1 ? 's' : ''} to Home Assistant`,
        });
      } else {
        toast.error('Publish failed', {
          description: result.message,
        });
      }
    } catch (error) {
      toast.error('Publish failed', {
        description: error instanceof Error ? error.message : 'Unknown error',
      });
    } finally {
      setIsPublishing(false);
    }
  };

  // Send test message handler
  const handleSendTestMessage = async () => {
    setIsSendingTestMessage(true);
    try {
      const result = await apiClient.mqtt.sendTestMessage();
      if (result.success) {
        toast.success('Test message sent', {
          description: `Published to ${result.topic}`,
        });
      } else {
        toast.error('Send failed', {
          description: result.message,
        });
      }
    } catch (error) {
      toast.error('Send failed', {
        description: error instanceof Error ? error.message : 'Unknown error',
      });
    } finally {
      setIsSendingTestMessage(false);
    }
  };

  // Save handler
  const handleSave = async (data: MQTTFormData) => {
    // Only send password if it was changed (not empty)
    const configUpdate: MQTTConfigUpdate = {
      ...data,
      password: data.password || undefined,
    };
    saveMutation.mutate(configUpdate);
  };

  // Status badge component (AC 4)
  const getStatusBadge = () => {
    if (statusQuery.isLoading) {
      return (
        <Badge variant="secondary">
          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
          Checking...
        </Badge>
      );
    }

    if (!form.watch('enabled')) {
      return (
        <Badge variant="secondary">
          <WifiOff className="mr-1 h-3 w-3" />
          Disabled
        </Badge>
      );
    }

    if (statusQuery.data?.connected) {
      return (
        <Badge variant="default" className="bg-green-600">
          <CheckCircle2 className="mr-1 h-3 w-3" />
          Connected
        </Badge>
      );
    }

    return (
      <Badge variant="destructive">
        <AlertTriangle className="mr-1 h-3 w-3" />
        Disconnected
      </Badge>
    );
  };

  if (configQuery.isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2">
              <Network className="h-5 w-5" />
              MQTT / Home Assistant
              <UnsavedIndicator isDirty={isDirty} />
            </CardTitle>
            <CardDescription>
              Connect to your MQTT broker for Home Assistant integration
            </CardDescription>
          </div>
          {getStatusBadge()}
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-6">
          {/* Master Enable Toggle */}
          <div className="flex items-center justify-between rounded-lg border p-4">
            <div className="space-y-0.5">
              <Label htmlFor="mqtt-enabled" className="text-base font-medium">
                Enable MQTT Integration
              </Label>
              <p className="text-sm text-muted-foreground">
                Publish events to MQTT broker and enable Home Assistant discovery
              </p>
            </div>
            <Switch
              id="mqtt-enabled"
              checked={form.watch('enabled')}
              onCheckedChange={(checked) => form.setValue('enabled', checked, { shouldDirty: true })}
            />
          </div>

          {/* Collapsible Configuration Sections (P8-3.1) */}
          <div
            data-testid="mqtt-config-sections"
            className={`grid transition-all duration-300 ease-in-out ${
              form.watch('enabled')
                ? 'grid-rows-[1fr] opacity-100'
                : 'grid-rows-[0fr] opacity-0'
            }`}
          >
            <div className="overflow-hidden">
              <div className="space-y-6">
                {/* Connection Status Display (AC 4) */}
                {statusQuery.data && (
                  <div className="rounded-lg bg-muted/50 p-4 space-y-2">
                    <div className="flex items-center gap-2">
                      {statusQuery.data.connected ? (
                        <Wifi className="h-4 w-4 text-green-600" />
                      ) : (
                        <WifiOff className="h-4 w-4 text-destructive" />
                      )}
                      <span className="font-medium">
                        {statusQuery.data.connected ? 'Connected' : 'Disconnected'}
                      </span>
                      {statusQuery.data.broker && (
                        <span className="text-sm text-muted-foreground">
                          to {statusQuery.data.broker}
                        </span>
                      )}
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div>
                        <span className="text-muted-foreground">Messages Published: </span>
                        <span className="font-medium">{statusQuery.data.messages_published.toLocaleString()}</span>
                      </div>
                      {statusQuery.data.reconnect_attempt > 0 && (
                        <div>
                          <span className="text-muted-foreground">Reconnect Attempts: </span>
                          <span className="font-medium">{statusQuery.data.reconnect_attempt}</span>
                        </div>
                      )}
                    </div>
                    {statusQuery.data.last_error && (
                      <Alert variant="destructive" className="mt-2">
                        <AlertTriangle className="h-4 w-4" />
                        <AlertDescription>{statusQuery.data.last_error}</AlertDescription>
                      </Alert>
                    )}
                  </div>
                )}

                {/* Broker Configuration (AC 2) */}
                <div className="space-y-4">
                  <h4 className="font-medium">Broker Connection</h4>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="md:col-span-2 space-y-2">
                      <Label htmlFor="broker_host">Broker Host</Label>
                      <Input
                        id="broker_host"
                        placeholder="192.168.1.100 or mqtt.example.com"
                        {...form.register('broker_host')}
                      />
                      {errors.broker_host && (
                        <p className="text-sm text-destructive">{errors.broker_host.message}</p>
                      )}
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="broker_port">Port</Label>
                      <Input
                        id="broker_port"
                        type="number"
                        placeholder="1883"
                        {...form.register('broker_port')}
                      />
                      {errors.broker_port && (
                        <p className="text-sm text-destructive">{errors.broker_port.message}</p>
                      )}
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="username">Username (optional)</Label>
                      <Input
                        id="username"
                        placeholder="mqtt_user"
                        autoComplete="username"
                        {...form.register('username')}
                      />
                    </div>
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <Label htmlFor="password">Password (optional)</Label>
                        {/* Password configured indicator (AC 9) */}
                        {configQuery.data?.has_password && !form.watch('password') && (
                          <Badge variant="secondary" className="text-xs">
                            <CheckCircle2 className="mr-1 h-3 w-3" />
                            Configured
                          </Badge>
                        )}
                      </div>
                      <div className="relative">
                        <Input
                          id="password"
                          type={showPassword ? 'text' : 'password'}
                          placeholder={configQuery.data?.has_password ? '••••••••' : 'Enter password'}
                          autoComplete="current-password"
                          {...form.register('password')}
                        />
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                          onClick={() => setShowPassword(!showPassword)}
                        >
                          {showPassword ? (
                            <EyeOff className="h-4 w-4 text-muted-foreground" />
                          ) : (
                            <Eye className="h-4 w-4 text-muted-foreground" />
                          )}
                        </Button>
                      </div>
                      {configQuery.data?.has_password && (
                        <p className="text-xs text-muted-foreground">
                          Leave empty to keep existing password
                        </p>
                      )}
                    </div>
                  </div>

                  {/* TLS Toggle */}
                  <div className="flex items-center justify-between rounded-lg border p-3">
                    <div className="space-y-0.5">
                      <Label htmlFor="use_tls">Use TLS/SSL</Label>
                      <p className="text-xs text-muted-foreground">
                        Enable secure connection (port 8883 is common for TLS)
                      </p>
                    </div>
                    <Switch
                      id="use_tls"
                      checked={form.watch('use_tls')}
                      onCheckedChange={(checked) => form.setValue('use_tls', checked, { shouldDirty: true })}
                    />
                  </div>

                  {/* Test Connection Button (AC 3) */}
                  <Button
                    type="button"
                    variant="outline"
                    onClick={handleTestConnection}
                    disabled={isTesting || !form.watch('broker_host')}
                  >
                    {isTesting ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Testing...
                      </>
                    ) : (
                      <>
                        <RefreshCw className="mr-2 h-4 w-4" />
                        Test Connection
                      </>
                    )}
                  </Button>
                </div>

                {/* Topic Configuration (AC 6) */}
                <div className="space-y-4">
                  <h4 className="font-medium">Topic Configuration</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="topic_prefix">Topic Prefix</Label>
                      <Input
                        id="topic_prefix"
                        placeholder="liveobject"
                        {...form.register('topic_prefix')}
                      />
                      {errors.topic_prefix && (
                        <p className="text-sm text-destructive">{errors.topic_prefix.message}</p>
                      )}
                      <p className="text-xs text-muted-foreground">
                        Events published to: {form.watch('topic_prefix')}/camera_name/event
                      </p>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="discovery_prefix">Discovery Prefix</Label>
                      <Input
                        id="discovery_prefix"
                        placeholder="homeassistant"
                        {...form.register('discovery_prefix')}
                      />
                      {errors.discovery_prefix && (
                        <p className="text-sm text-destructive">{errors.discovery_prefix.message}</p>
                      )}
                      <p className="text-xs text-muted-foreground">
                        Home Assistant default: homeassistant
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="qos">Quality of Service (QoS)</Label>
                      <Select
                        value={String(form.watch('qos'))}
                        onValueChange={(value) => form.setValue('qos', parseInt(value) as 0 | 1 | 2, { shouldDirty: true })}
                      >
                        <SelectTrigger id="qos">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="0">0 - At most once</SelectItem>
                          <SelectItem value="1">1 - At least once (recommended)</SelectItem>
                          <SelectItem value="2">2 - Exactly once</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="flex items-center justify-between rounded-lg border p-3 h-fit">
                      <div className="space-y-0.5">
                        <Label htmlFor="retain_messages">Retain Messages</Label>
                        <p className="text-xs text-muted-foreground">Keep last message on broker</p>
                      </div>
                      <Switch
                        id="retain_messages"
                        checked={form.watch('retain_messages')}
                        onCheckedChange={(checked) => form.setValue('retain_messages', checked, { shouldDirty: true })}
                      />
                    </div>
                  </div>

                  {/* Message Expiry (P5-6.1) */}
                  <div className="space-y-2">
                    <Label htmlFor="message_expiry_seconds">Message Expiry (seconds)</Label>
                    <Input
                      id="message_expiry_seconds"
                      type="number"
                      min={60}
                      max={3600}
                      placeholder="300"
                      {...form.register('message_expiry_seconds')}
                    />
                    {errors.message_expiry_seconds && (
                      <p className="text-sm text-destructive">{errors.message_expiry_seconds.message}</p>
                    )}
                    <p className="text-xs text-muted-foreground">
                      MQTT 5.0 message expiry interval (60-3600 seconds). Messages not consumed within this time are discarded by the broker.
                    </p>
                  </div>
                </div>

                {/* Availability Messages (P5-6.2) */}
                <div className="space-y-4">
                  <h4 className="font-medium">Availability Messages</h4>
                  <p className="text-sm text-muted-foreground">
                    Birth and will messages announce ArgusAI&apos;s connection state to Home Assistant.
                    The broker publishes the will message if ArgusAI disconnects unexpectedly.
                  </p>

                  <div className="space-y-2">
                    <Label htmlFor="availability_topic">Availability Topic</Label>
                    <Input
                      id="availability_topic"
                      placeholder={`${form.watch('topic_prefix')}/status`}
                      {...form.register('availability_topic')}
                    />
                    {errors.availability_topic && (
                      <p className="text-sm text-destructive">{errors.availability_topic.message}</p>
                    )}
                    <p className="text-xs text-muted-foreground">
                      Topic for online/offline status. Leave empty to use default: {form.watch('topic_prefix')}/status
                    </p>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="birth_message">Birth Message (online)</Label>
                      <Input
                        id="birth_message"
                        placeholder="online"
                        {...form.register('birth_message')}
                      />
                      {errors.birth_message && (
                        <p className="text-sm text-destructive">{errors.birth_message.message}</p>
                      )}
                      <p className="text-xs text-muted-foreground">
                        Published when ArgusAI connects
                      </p>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="will_message">Will Message (offline)</Label>
                      <Input
                        id="will_message"
                        placeholder="offline"
                        {...form.register('will_message')}
                      />
                      {errors.will_message && (
                        <p className="text-sm text-destructive">{errors.will_message.message}</p>
                      )}
                      <p className="text-xs text-muted-foreground">
                        Published when ArgusAI disconnects
                      </p>
                    </div>
                  </div>
                </div>

                {/* Home Assistant Discovery (AC 7) */}
                <div className="space-y-4">
                  <h4 className="font-medium">Home Assistant Discovery</h4>
                  <div className="flex items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <Label htmlFor="discovery_enabled" className="text-base">
                        Enable Auto-Discovery
                      </Label>
                      <p className="text-sm text-muted-foreground">
                        Automatically register cameras as sensors in Home Assistant
                      </p>
                    </div>
                    <Switch
                      id="discovery_enabled"
                      checked={form.watch('discovery_enabled')}
                      onCheckedChange={(checked) => form.setValue('discovery_enabled', checked, { shouldDirty: true })}
                    />
                  </div>

                  {/* Publish Discovery Button (AC 10) */}
                  {form.watch('discovery_enabled') && (
                    <div className="flex items-center justify-between rounded-lg border p-4">
                      <div className="space-y-0.5">
                        <p className="text-sm font-medium">Manual Discovery Publish</p>
                        <p className="text-sm text-muted-foreground">
                          Re-publish discovery configs for all cameras
                        </p>
                      </div>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={handlePublishDiscovery}
                        disabled={isPublishing || !statusQuery.data?.connected}
                      >
                        {isPublishing ? (
                          <>
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            Publishing...
                          </>
                        ) : (
                          <>
                            <Send className="mr-2 h-4 w-4" />
                            Publish Discovery
                          </>
                        )}
                      </Button>
                    </div>
                  )}

                  {/* Send Test Message Button */}
                  <div className="flex items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <p className="text-sm font-medium">Send Test Alert</p>
                      <p className="text-sm text-muted-foreground">
                        Publish a test message to verify MQTT integration
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={handleSendTestMessage}
                      disabled={isSendingTestMessage || !statusQuery.data?.connected}
                    >
                      {isSendingTestMessage ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Sending...
                        </>
                      ) : (
                        <>
                          <Bell className="mr-2 h-4 w-4" />
                          Send Test
                        </>
                      )}
                    </Button>
                  </div>
                </div>

                {/* Info Alert - Story P9-6.6: Only visible when MQTT enabled */}
                <Alert>
                  <Info className="h-4 w-4" />
                  <AlertTitle>Home Assistant Integration</AlertTitle>
                  <AlertDescription>
                    When enabled, detected events are published to MQTT and cameras are auto-discovered
                    as sensors in Home Assistant. Events include camera name, description, timestamp,
                    and detection type.
                  </AlertDescription>
                </Alert>
              </div>
            </div>
          </div>

          {/* Save Button (AC 5) - Story P9-6.6: Only visible when MQTT enabled or form is dirty */}
          {(form.watch('enabled') || isDirty) && (
            <div className="flex justify-end gap-2">
              {isDirty && (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => form.reset()}
                  disabled={saveMutation.isPending}
                >
                  Cancel
                </Button>
              )}
              <Button
                type="button"
                onClick={form.handleSubmit(handleSave)}
                disabled={saveMutation.isPending || !isDirty}
              >
                {saveMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Saving...
                  </>
                ) : (
                  'Save Changes'
                )}
              </Button>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
