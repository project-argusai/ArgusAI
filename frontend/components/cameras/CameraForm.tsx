/**
 * Camera form component with validation, conditional fields, and test connection
 */

'use client';
'use no memo'; // React Hook Form's watch() API is incompatible with React Compiler memoization

import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2, CheckCircle2, XCircle } from 'lucide-react';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cameraFormSchema, type CameraFormValues } from '@/lib/validations/camera';
import type { ICamera, ICameraTestResponse, IDetectionZone, IZoneVertex } from '@/types/camera';
import type { ITestConnectionResponse } from '@/types/discovery';
import { apiClient, ApiError } from '@/lib/api-client';
import { MotionSettingsSection } from './MotionSettingsSection';
import { AudioSettingsSection } from './AudioSettingsSection';
import { DetectionZoneDrawer } from './DetectionZoneDrawer';
import { DetectionZoneList } from './DetectionZoneList';
import { ZonePresetTemplates } from './ZonePresetTemplates';
import { DetectionScheduleEditor } from './DetectionScheduleEditor';
import { AnalysisModeSelector } from './AnalysisModeSelector';
import { HomeKitStreamQualitySelector } from './HomeKitStreamQualitySelector';

interface CameraFormProps {
  /**
   * Initial data for edit mode
   */
  initialData?: ICamera;
  /**
   * Form submission handler
   */
  onSubmit: (data: CameraFormValues) => Promise<void>;
  /**
   * Cancel handler
   */
  onCancel?: () => void;
  /**
   * Whether form is submitting
   */
  isSubmitting?: boolean;
}

/**
 * Camera creation/edit form component
 */
export function CameraForm({
  initialData,
  onSubmit,
  onCancel,
  isSubmitting,
}: CameraFormProps) {
  const isEditMode = !!initialData;

  // Test connection state - supports both new cameras (discovery API) and existing cameras
  const [testState, setTestState] = useState<{
    loading: boolean;
    result: (ICameraTestResponse & Partial<ITestConnectionResponse>) | null;
  }>({ loading: false, result: null });

  // Zone drawing state
  const [isDrawingZone, setIsDrawingZone] = useState(false);
  const [zones, setZones] = useState<IDetectionZone[]>(initialData?.detection_zones || []);

  // Form setup with React Hook Form + Zod
  const form = useForm<CameraFormValues>({
    resolver: zodResolver(cameraFormSchema),
    defaultValues: initialData
      ? {
          name: initialData.name,
          type: initialData.type,
          rtsp_url: initialData.rtsp_url,
          username: initialData.username,
          device_index: initialData.device_index,
          frame_rate: initialData.frame_rate,
          is_enabled: initialData.is_enabled,
          motion_enabled: initialData.motion_enabled,
          motion_sensitivity: initialData.motion_sensitivity,
          motion_cooldown: initialData.motion_cooldown,
          motion_algorithm: initialData.motion_algorithm,
          detection_zones: initialData.detection_zones || [],
          detection_schedule: initialData.detection_schedule || {
            enabled: false,
            start_time: '09:00',
            end_time: '17:00',
            days: [0, 1, 2, 3, 4],
          },
          analysis_mode: initialData.analysis_mode || 'single_frame',
          // Phase 7: HomeKit stream quality
          homekit_stream_quality: initialData.homekit_stream_quality || 'medium',
          // Phase 6: Audio settings
          audio_enabled: initialData.audio_enabled ?? false,
          audio_event_types: (initialData.audio_event_types ?? []) as Array<'glass_break' | 'gunshot' | 'scream' | 'doorbell'>,
          audio_threshold: initialData.audio_threshold ?? null,
        }
      : {
          name: '',
          type: 'rtsp',
          frame_rate: 5,
          is_enabled: true,
          motion_enabled: true,
          motion_sensitivity: 'medium',
          motion_cooldown: 30,
          motion_algorithm: 'mog2',
          detection_zones: [],
          detection_schedule: {
            enabled: false,
            start_time: '09:00',
            end_time: '17:00',
            days: [0, 1, 2, 3, 4],
          },
          analysis_mode: 'single_frame',
          // Phase 7: HomeKit stream quality (default medium for new cameras)
          homekit_stream_quality: 'medium',
          // Phase 6: Audio settings (default disabled for new cameras)
          audio_enabled: false,
          audio_event_types: [],
          audio_threshold: null,
        },
  });

  const cameraType = form.watch('type');
  const frameRate = form.watch('frame_rate');

  /**
   * Test camera connection
   * For new cameras: Uses discovery.testConnection with form values
   * For existing cameras: Uses cameras.testConnection with camera ID
   */
  const handleTestConnection = async () => {
    setTestState({ loading: true, result: null });

    try {
      if (initialData) {
        // Existing camera: use camera ID endpoint
        const result = await apiClient.cameras.test(Number(initialData.id));
        setTestState({ loading: false, result });
      } else {
        // New camera: use discovery test endpoint with form values
        const rtspUrl = form.getValues('rtsp_url');
        const username = form.getValues('username');
        const password = form.getValues('password');

        if (!rtspUrl) {
          setTestState({
            loading: false,
            result: {
              success: false,
              message: 'Enter an RTSP URL first',
            },
          });
          return;
        }

        const result = await apiClient.discovery.testConnection(
          rtspUrl,
          username || password ? { username: username || undefined, password: password || undefined } : undefined
        );

        // Map discovery response to camera test response format
        setTestState({
          loading: false,
          result: {
            success: result.success,
            message: result.success
              ? `Connected: ${result.resolution || 'Unknown resolution'} @ ${result.fps || '?'}fps${result.codec ? ` (${result.codec})` : ''}`
              : result.error || 'Connection test failed',
            resolution: result.resolution,
            fps: result.fps,
            codec: result.codec,
            latency_ms: result.latency_ms,
          },
        });
      }
    } catch (err) {
      setTestState({
        loading: false,
        result: {
          success: false,
          message:
            err instanceof ApiError
              ? err.message
              : 'Connection test failed',
        },
      });
    }
  };

  /**
   * Handle zone drawing completion
   */
  const handleZoneComplete = (vertices: IZoneVertex[]) => {
    const newZone: IDetectionZone = {
      id: `zone-${Date.now()}`,
      name: `Zone ${zones.length + 1}`,
      vertices,
      enabled: true,
    };

    const updatedZones = [...zones, newZone];
    setZones(updatedZones);
    form.setValue('detection_zones', updatedZones);
    setIsDrawingZone(false);
  };

  /**
   * Handle preset template selection
   * @param vertices - Preset vertices in normalized 0-1 coordinates
   * @param name - Preset name (e.g., "Full Frame")
   */
  const handleTemplateSelect = (vertices: IZoneVertex[], name: string) => {
    const newZone: IDetectionZone = {
      id: `zone-${Date.now()}`,
      name: `${name} Zone`,
      vertices,
      enabled: true,
    };

    const updatedZones = [...zones, newZone];
    setZones(updatedZones);
    form.setValue('detection_zones', updatedZones);
  };

  /**
   * Handle zone update (name, enabled)
   */
  const handleZoneUpdate = (zoneId: string, updates: Partial<IDetectionZone>) => {
    const updatedZones = zones.map((zone) =>
      zone.id === zoneId ? { ...zone, ...updates } : zone
    );
    setZones(updatedZones);
    form.setValue('detection_zones', updatedZones);
  };

  /**
   * Handle zone deletion
   */
  const handleZoneDelete = (zoneId: string) => {
    const updatedZones = zones.filter((zone) => zone.id !== zoneId);
    setZones(updatedZones);
    form.setValue('detection_zones', updatedZones);
  };

  // Debug form state
  React.useEffect(() => {
    console.log('Form state:', {
      isValid: form.formState.isValid,
      isDirty: form.formState.isDirty,
      errors: form.formState.errors,
      values: form.getValues(),
    });
  }, [form.formState, form]);

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        {/* Camera Name */}
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Camera Name</FormLabel>
              <FormControl>
                <Input placeholder="Front Door Camera" {...field} />
              </FormControl>
              <FormDescription>
                A friendly name for this camera (1-100 characters)
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {/* Camera Type */}
        <FormField
          control={form.control}
          name="type"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Camera Type</FormLabel>
              <Select
                onValueChange={field.onChange}
                defaultValue={field.value}
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder="Select camera type" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  <SelectItem value="rtsp">RTSP Camera</SelectItem>
                  <SelectItem value="usb">USB Camera</SelectItem>
                </SelectContent>
              </Select>
              <FormDescription>
                RTSP for network cameras, USB for webcams
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {/* RTSP Fields (conditional) */}
        {cameraType === 'rtsp' && (
          <>
            <FormField
              control={form.control}
              name="rtsp_url"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>RTSP URL</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="rtsp://192.168.1.50:554/stream1"
                      {...field}
                      value={field.value ?? ''}
                    />
                  </FormControl>
                  <FormDescription>
                    Full RTSP URL (must start with rtsp:// or rtsps://)
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="username"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Username (Optional)</FormLabel>
                    <FormControl>
                      <Input placeholder="admin" {...field} value={field.value ?? ''} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Password (Optional)</FormLabel>
                    <FormControl>
                      <Input type="password" {...field} value={field.value ?? ''} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
          </>
        )}

        {/* USB Fields (conditional) */}
        {cameraType === 'usb' && (
          <FormField
            control={form.control}
            name="device_index"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Device Index</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    min={0}
                    placeholder="0"
                    {...field}
                    onChange={(e) =>
                      field.onChange(
                        e.target.value ? parseInt(e.target.value) : undefined
                      )
                    }
                    value={field.value ?? ''}
                  />
                </FormControl>
                <FormDescription>
                  USB camera index (0 for first camera, 1 for second, etc.)
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

        {/* Frame Rate Slider */}
        <FormField
          control={form.control}
          name="frame_rate"
          render={({ field}) => (
            <FormItem>
              <FormLabel>Frame Rate: {frameRate} FPS</FormLabel>
              <FormControl>
                <Slider
                  min={1}
                  max={30}
                  step={1}
                  value={[field.value]}
                  onValueChange={(values) => field.onChange(values[0])}
                  className="w-full"
                />
              </FormControl>
              <FormDescription>
                Target frames per second (1-30)
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {/* Motion Detection Settings */}
        <MotionSettingsSection form={form} />

        {/* Detection Zones */}
        <div className="border rounded-lg p-6 bg-muted/10 space-y-4">
          <div>
            <h3 className="font-medium text-lg">Detection Zones</h3>
            <p className="text-sm text-muted-foreground mt-1">
              Define specific areas where motion detection should be active (max 10 zones)
            </p>
          </div>

          {/* Zone List */}
          <DetectionZoneList
            zones={zones}
            onZoneUpdate={handleZoneUpdate}
            onZoneDelete={handleZoneDelete}
          />

          {/* Draw Zone Section */}
          {!isDrawingZone && zones.length < 10 && (
            <div className="space-y-3">
              <ZonePresetTemplates onTemplateSelect={handleTemplateSelect} />
              <div className="flex justify-center">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsDrawingZone(true)}
                >
                  Draw Custom Polygon
                </Button>
              </div>
            </div>
          )}

          {isDrawingZone && (
            <DetectionZoneDrawer
              zones={zones}
              onZoneComplete={handleZoneComplete}
              onCancel={() => setIsDrawingZone(false)}
              previewImage={testState.result?.thumbnail}
            />
          )}

          {zones.length >= 10 && (
            <p className="text-sm text-amber-600 font-medium text-center">
              Maximum of 10 zones reached
            </p>
          )}
        </div>

        {/* Detection Schedule */}
        <DetectionScheduleEditor form={form} />

        {/* AI Analysis Mode */}
        <AnalysisModeSelector
          form={form}
          sourceType={initialData?.source_type || cameraType}
        />

        {/* HomeKit Stream Quality */}
        <HomeKitStreamQualitySelector form={form} />

        {/* Audio Detection Settings - only for RTSP cameras */}
        {cameraType === 'rtsp' && (
          <AudioSettingsSection form={form} />
        )}

        {/* Test Connection Button - available for RTSP cameras (both new and edit mode) */}
        {(cameraType === 'rtsp' || isEditMode) && (
          <div className="border rounded-lg p-4 bg-muted/20">
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="font-medium">Test Connection</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  {isEditMode
                    ? 'Verify camera connectivity and see a preview'
                    : 'Test RTSP connection before saving'}
                </p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleTestConnection}
                disabled={testState.loading || (cameraType === 'rtsp' && !form.watch('rtsp_url'))}
              >
                {testState.loading && (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                )}
                Test
              </Button>
            </div>

            {/* Test Result */}
            {testState.result && (
              <div
                className={`mt-3 p-3 rounded-md ${
                  testState.result.success
                    ? 'bg-green-50 border border-green-200 dark:bg-green-950 dark:border-green-800'
                    : 'bg-red-50 border border-red-200 dark:bg-red-950 dark:border-red-800'
                }`}
              >
                <div className="flex items-start gap-2">
                  {testState.result.success ? (
                    <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400 flex-shrink-0 mt-0.5" />
                  ) : (
                    <XCircle className="h-5 w-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                  )}
                  <div className="flex-1">
                    <p
                      className={`text-sm font-medium ${
                        testState.result.success
                          ? 'text-green-900 dark:text-green-100'
                          : 'text-red-900 dark:text-red-100'
                      }`}
                    >
                      {testState.result.message}
                    </p>
                    {/* Show latency for new camera tests */}
                    {testState.result.success && testState.result.latency_ms && (
                      <p className="text-xs text-muted-foreground mt-1">
                        Latency: {testState.result.latency_ms}ms
                      </p>
                    )}
                    {testState.result.thumbnail && (
                      <img
                        src={testState.result.thumbnail}
                        alt="Camera preview"
                        className="mt-3 rounded-md border max-w-xs"
                      />
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Form Actions */}
        <div className="flex gap-3 pt-4">
          {onCancel && (
            <Button
              type="button"
              variant="outline"
              onClick={onCancel}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
          )}
          <Button type="submit" disabled={isSubmitting} className="flex-1">
            {isSubmitting && (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            )}
            {isEditMode ? 'Update Camera' : 'Save Camera'}
          </Button>
        </div>
      </form>
    </Form>
  );
}
