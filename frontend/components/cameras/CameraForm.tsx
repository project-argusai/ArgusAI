/**
 * Camera form component with validation, conditional fields, and test connection
 */

'use client';

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
import { apiClient, ApiError } from '@/lib/api-client';
import { MotionSettingsSection } from './MotionSettingsSection';
import { DetectionZoneDrawer } from './DetectionZoneDrawer';
import { DetectionZoneList } from './DetectionZoneList';
import { ZonePresetTemplates } from './ZonePresetTemplates';
import { DetectionScheduleEditor } from './DetectionScheduleEditor';

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

  // Test connection state
  const [testState, setTestState] = useState<{
    loading: boolean;
    result: ICameraTestResponse | null;
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
        },
  });

  const cameraType = form.watch('type');
  const frameRate = form.watch('frame_rate');

  /**
   * Test camera connection
   * Note: For new cameras, this would require a temporary test endpoint
   * For existing cameras, we can use the camera ID
   */
  const handleTestConnection = async () => {
    if (!initialData) {
      // For new cameras, show info that test is only available after saving
      setTestState({
        loading: false,
        result: {
          success: false,
          message: 'Save the camera first to test connection',
        },
      });
      return;
    }

    setTestState({ loading: true, result: null });

    try {
      const result = await apiClient.cameras.testConnection(initialData.id);
      setTestState({ loading: false, result });
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
   */
  const handleTemplateSelect = (vertices: IZoneVertex[]) => {
    handleZoneComplete(vertices);
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

        {/* Test Connection Button (edit mode only) */}
        {isEditMode && (
          <div className="border rounded-lg p-4 bg-muted/20">
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="font-medium">Test Connection</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  Verify camera connectivity and see a preview
                </p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleTestConnection}
                disabled={testState.loading}
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
                    ? 'bg-green-50 border border-green-200'
                    : 'bg-red-50 border border-red-200'
                }`}
              >
                <div className="flex items-start gap-2">
                  {testState.result.success ? (
                    <CheckCircle2 className="h-5 w-5 text-green-600 flex-shrink-0 mt-0.5" />
                  ) : (
                    <XCircle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
                  )}
                  <div className="flex-1">
                    <p
                      className={`text-sm font-medium ${
                        testState.result.success
                          ? 'text-green-900'
                          : 'text-red-900'
                      }`}
                    >
                      {testState.result.message}
                    </p>
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
