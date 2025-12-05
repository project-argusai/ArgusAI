/**
 * UniFi Protect Controller Form Component
 * Story P2-1.3: Controller Configuration UI
 * Story P2-1.5: Edit mode with optional password
 *
 * Form for adding or editing a UniFi Protect controller with:
 * - Name, Host, Username, Password, Verify SSL fields
 * - Test Connection button
 * - Save button (enabled after successful test)
 * - Real-time validation on blur
 * - Edit mode: pre-populates values, password optional
 */

'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, CheckCircle2, XCircle, Shield } from 'lucide-react';

import { apiClient, ApiError } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ConnectionStatus, type ConnectionStatusType } from './ConnectionStatus';

// Controller data for edit mode
export interface ControllerData {
  id: string;
  name: string;
  host: string;
  port: number;
  username: string;
  verify_ssl: boolean;
  is_connected: boolean;
}

// Zod schema - password required for create, optional for edit
const createControllerFormSchema = (isEditMode: boolean) => z.object({
  name: z
    .string()
    .min(1, 'Name is required')
    .max(100, 'Name must be 100 characters or less'),
  host: z
    .string()
    .min(1, 'Host is required')
    .max(255, 'Host must be 255 characters or less'),
  port: z
    .number()
    .int()
    .min(1, 'Port must be between 1 and 65535')
    .max(65535, 'Port must be between 1 and 65535'),
  username: z
    .string()
    .min(1, 'Username is required')
    .max(100, 'Username must be 100 characters or less'),
  password: isEditMode
    ? z.string().max(100, 'Password must be 100 characters or less').optional().or(z.literal(''))
    : z.string().min(1, 'Password is required').max(100, 'Password must be 100 characters or less'),
  verify_ssl: z.boolean(),
});

type ControllerFormData = z.infer<ReturnType<typeof createControllerFormSchema>>;

interface ControllerFormProps {
  controller?: ControllerData; // If provided, form is in edit mode
  onSaveSuccess?: (controller: { id: string; name: string }) => void;
  onCancel?: () => void;
}

export function ControllerForm({ controller, onSaveSuccess, onCancel }: ControllerFormProps) {
  const isEditMode = !!controller;
  const queryClient = useQueryClient();

  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatusType>(
    isEditMode && controller.is_connected ? 'connected' : 'not_configured'
  );
  const [testResult, setTestResult] = useState<{
    firmwareVersion?: string;
    cameraCount?: number;
    errorMessage?: string;
  }>({});
  const [connectionTested, setConnectionTested] = useState(isEditMode); // In edit mode, assume already tested
  const [passwordChanged, setPasswordChanged] = useState(false);

  const form = useForm<ControllerFormData>({
    resolver: zodResolver(createControllerFormSchema(isEditMode)),
    defaultValues: {
      name: controller?.name ?? '',
      host: controller?.host ?? '',
      port: controller?.port ?? 443,
      username: controller?.username ?? '',
      password: '', // Never pre-populate password (security)
      verify_ssl: controller?.verify_ssl ?? false,
    },
    mode: 'onBlur', // Validate on blur per AC7
  });

  const { formState: { errors, dirtyFields } } = form;

  // Reset test status when form values change
  const handleFieldChange = (fieldName?: string) => {
    if (connectionTested && !isEditMode) {
      setConnectionTested(false);
      setConnectionStatus('not_configured');
      setTestResult({});
    }
    // Track if password was changed in edit mode
    if (fieldName === 'password') {
      setPasswordChanged(true);
    }
  };

  // Test connection mutation - handles both new and existing credentials
  const testConnectionMutation = useMutation({
    mutationFn: async (data: ControllerFormData) => {
      // In edit mode with no password change, test using existing controller
      if (isEditMode && !passwordChanged && !data.password) {
        return apiClient.protect.testExistingController(controller.id);
      }
      // Otherwise test with provided credentials
      return apiClient.protect.testConnection({
        host: data.host,
        port: data.port,
        username: data.username,
        password: data.password || '',
        verify_ssl: data.verify_ssl,
      });
    },
    onMutate: () => {
      setConnectionStatus('connecting');
      setTestResult({});
    },
    onSuccess: (response) => {
      if (response.data.success) {
        setConnectionStatus('connected');
        setTestResult({
          firmwareVersion: response.data.firmware_version,
          cameraCount: response.data.camera_count,
        });
        setConnectionTested(true);
        toast.success('Connection successful!');
      } else {
        setConnectionStatus('error');
        setTestResult({ errorMessage: response.data.message });
        toast.error(response.data.message || 'Connection failed');
      }
    },
    onError: (error: Error) => {
      setConnectionStatus('error');
      let errorMessage = 'Connection failed';

      if (error instanceof ApiError) {
        // Map HTTP status codes to user-friendly messages
        switch (error.statusCode) {
          case 401:
            errorMessage = 'Authentication failed - check username and password';
            break;
          case 502:
            errorMessage = 'SSL certificate verification failed - try disabling SSL verification';
            break;
          case 503:
            errorMessage = 'Host unreachable - check the IP address or hostname';
            break;
          case 504:
            errorMessage = 'Connection timed out - the controller may be offline';
            break;
          default:
            errorMessage = error.message || 'Connection failed';
        }
      }

      setTestResult({ errorMessage });
      toast.error(errorMessage);
    },
  });

  // Save controller mutation (create or update)
  const saveControllerMutation = useMutation({
    mutationFn: async (data: ControllerFormData) => {
      if (isEditMode) {
        // Only send changed fields for update (partial update)
        const updateData: Record<string, unknown> = {};

        if (dirtyFields.name) updateData.name = data.name;
        if (dirtyFields.host) updateData.host = data.host;
        if (dirtyFields.port) updateData.port = data.port;
        if (dirtyFields.username) updateData.username = data.username;
        if (dirtyFields.verify_ssl) updateData.verify_ssl = data.verify_ssl;
        // Only include password if it was actually changed (not empty)
        if (passwordChanged && data.password) {
          updateData.password = data.password;
        }

        return apiClient.protect.updateController(controller.id, updateData);
      } else {
        // Create new controller
        return apiClient.protect.createController({
          name: data.name,
          host: data.host,
          port: data.port,
          username: data.username,
          password: data.password || '',
          verify_ssl: data.verify_ssl,
        });
      }
    },
    onSuccess: (response) => {
      // Invalidate controller queries to refresh data
      queryClient.invalidateQueries({ queryKey: ['protectControllers'] });

      toast.success(isEditMode ? 'Controller updated successfully' : 'Controller saved successfully');
      onSaveSuccess?.({ id: response.data.id, name: response.data.name });
    },
    onError: (error: Error) => {
      let errorMessage = isEditMode ? 'Failed to update controller' : 'Failed to save controller';

      if (error instanceof ApiError) {
        if (error.statusCode === 409) {
          errorMessage = 'A controller with this name already exists';
        } else {
          errorMessage = error.message || errorMessage;
        }
      }

      toast.error(errorMessage);
    },
  });

  const handleTestConnection = async () => {
    // Validate form first (for edit mode, password is optional)
    const isFormValid = await form.trigger();
    if (!isFormValid) {
      toast.error('Please fix form errors before testing');
      return;
    }

    const data = form.getValues();
    testConnectionMutation.mutate(data);
  };

  const handleSave = async () => {
    const isFormValid = await form.trigger();
    if (!isFormValid) {
      toast.error('Please fix form errors before saving');
      return;
    }

    const data = form.getValues();
    saveControllerMutation.mutate(data);
  };

  const isTestingConnection = testConnectionMutation.isPending;
  const isSaving = saveControllerMutation.isPending;
  // In edit mode, can save even without testing if no connection fields changed
  const connectionFieldsDirty = dirtyFields.host || dirtyFields.port || dirtyFields.username || passwordChanged || dirtyFields.verify_ssl;
  const canSave = isEditMode
    ? (!connectionFieldsDirty || (connectionTested && connectionStatus === 'connected')) && !isSaving
    : connectionTested && connectionStatus === 'connected' && !isSaving;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="h-5 w-5 text-cyan-500" />
            <CardTitle>{isEditMode ? 'Edit Controller' : 'Controller Connection'}</CardTitle>
          </div>
          <ConnectionStatus
            status={connectionStatus}
            errorMessage={testResult.errorMessage}
            firmwareVersion={testResult.firmwareVersion}
            cameraCount={testResult.cameraCount}
          />
        </div>
        <CardDescription>
          {isEditMode
            ? 'Update your UniFi Protect controller settings'
            : 'Enter your UniFi Protect controller details to connect'
          }
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Name Field */}
          <div className="space-y-2">
            <Label htmlFor="controller-name">
              Name <span className="text-red-500">*</span>
            </Label>
            <Input
              id="controller-name"
              placeholder="Home UDM Pro"
              {...form.register('name', { onChange: () => handleFieldChange() })}
              className={errors.name ? 'border-red-500' : ''}
            />
            <p className="text-xs text-muted-foreground">
              A friendly name to identify this controller (e.g., &quot;Home UDM Pro&quot;, &quot;Office Cloud Key&quot;)
            </p>
            {errors.name && (
              <p className="text-sm text-red-500">{errors.name.message}</p>
            )}
          </div>

          {/* Host Field */}
          <div className="space-y-2">
            <Label htmlFor="controller-host">
              Host / IP Address <span className="text-red-500">*</span>
            </Label>
            <Input
              id="controller-host"
              placeholder="192.168.1.1 or unifi.local"
              {...form.register('host', { onChange: () => handleFieldChange() })}
              className={errors.host ? 'border-red-500' : ''}
            />
            <p className="text-xs text-muted-foreground">
              The IP address or hostname of your UDM, Cloud Key, or NVR (e.g., 192.168.1.1)
            </p>
            {errors.host && (
              <p className="text-sm text-red-500">{errors.host.message}</p>
            )}
          </div>

          {/* Port Field */}
          <div className="space-y-2">
            <Label htmlFor="controller-port">Port</Label>
            <Input
              id="controller-port"
              type="number"
              placeholder="443"
              {...form.register('port', {
                valueAsNumber: true,
                onChange: () => handleFieldChange()
              })}
              className={errors.port ? 'border-red-500' : ''}
            />
            <p className="text-xs text-muted-foreground">
              Default is 443. Only change if your controller uses a non-standard HTTPS port.
            </p>
            {errors.port && (
              <p className="text-sm text-red-500">{errors.port.message}</p>
            )}
          </div>

          {/* Username Field */}
          <div className="space-y-2">
            <Label htmlFor="controller-username">
              Username <span className="text-red-500">*</span>
            </Label>
            <Input
              id="controller-username"
              placeholder="admin"
              autoComplete="username"
              {...form.register('username', { onChange: () => handleFieldChange() })}
              className={errors.username ? 'border-red-500' : ''}
            />
            <p className="text-xs text-muted-foreground">
              A local Protect account username. Cloud/Ubiquiti SSO accounts are not supported.
            </p>
            {errors.username && (
              <p className="text-sm text-red-500">{errors.username.message}</p>
            )}
          </div>

          {/* Password Field */}
          <div className="space-y-2">
            <Label htmlFor="controller-password">
              Password {!isEditMode && <span className="text-red-500">*</span>}
            </Label>
            <Input
              id="controller-password"
              type="password"
              placeholder={isEditMode ? '••••••••' : ''}
              autoComplete="current-password"
              {...form.register('password', { onChange: () => handleFieldChange('password') })}
              className={errors.password ? 'border-red-500' : ''}
            />
            {errors.password && (
              <p className="text-sm text-red-500">{errors.password.message}</p>
            )}
            {isEditMode && (
              <p className="text-xs text-muted-foreground">
                Leave blank to keep the existing password
              </p>
            )}
          </div>

          {/* Verify SSL Checkbox */}
          <div className="flex items-center justify-between p-3 rounded-lg border">
            <div className="flex-1">
              <Label htmlFor="verify-ssl" className="cursor-pointer">
                Verify SSL Certificate
              </Label>
              <p className="text-xs text-muted-foreground">
                Disable if using self-signed certificates (common for local UniFi deployments)
              </p>
            </div>
            <Switch
              id="verify-ssl"
              checked={form.watch('verify_ssl')}
              onCheckedChange={(checked) => {
                form.setValue('verify_ssl', checked, { shouldDirty: true });
                handleFieldChange();
              }}
            />
          </div>

          {/* Action Buttons */}
          <div className="flex flex-col sm:flex-row gap-3 pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={handleTestConnection}
              disabled={isTestingConnection || isSaving}
              className="flex-1 bg-cyan-50 hover:bg-cyan-100 border-cyan-200 text-cyan-700"
            >
              {isTestingConnection && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              {connectionStatus === 'connected' && <CheckCircle2 className="h-4 w-4 mr-2 text-green-600" />}
              {connectionStatus === 'error' && <XCircle className="h-4 w-4 mr-2 text-red-600" />}
              Test Connection
            </Button>

            <Button
              type="button"
              onClick={handleSave}
              disabled={!canSave}
              className="flex-1"
            >
              {isSaving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              {isEditMode ? 'Save Changes' : 'Save Controller'}
            </Button>
          </div>

          {/* Help Text */}
          {!connectionTested && !isEditMode && (
            <p className="text-xs text-muted-foreground text-center">
              Test the connection before saving to verify your credentials
            </p>
          )}
          {isEditMode && connectionFieldsDirty && !connectionTested && (
            <p className="text-xs text-muted-foreground text-center">
              Connection settings changed - test the connection to verify
            </p>
          )}

          {/* Cancel Button (if onCancel provided) */}
          {onCancel && (
            <Button
              type="button"
              variant="ghost"
              onClick={onCancel}
              className="w-full"
              disabled={isSaving}
            >
              Cancel
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
