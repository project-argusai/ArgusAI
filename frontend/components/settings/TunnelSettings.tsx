/**
 * TunnelSettings component (Story P11-1.3)
 *
 * Settings UI for Cloudflare Tunnel integration with:
 * - Enable/disable toggle (AC-1.3.2)
 * - Secure token input with show/hide (AC-1.3.3)
 * - Status indicator (AC-1.3.4)
 * - Test connection button (AC-1.3.5)
 * - Uptime, last connected, reconnect count display
 */

'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Cloud,
  CloudOff,
  Loader2,
  Eye,
  EyeOff,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  ExternalLink,
  Clock,
  Activity,
} from 'lucide-react';

import { apiClient, type TunnelStatus } from '@/lib/api-client';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';

/**
 * Format seconds to human-readable uptime string
 */
function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
}

/**
 * Format ISO date to relative time
 */
function formatLastConnected(isoDate: string | null): string {
  if (!isoDate) return 'Never';
  const date = new Date(isoDate);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

export function TunnelSettings() {
  const queryClient = useQueryClient();
  const [showToken, setShowToken] = useState(false);
  const [tokenInput, setTokenInput] = useState('');
  const [isTesting, setIsTesting] = useState(false);

  // Fetch tunnel status with polling
  const statusQuery = useQuery({
    queryKey: ['tunnel-status'],
    queryFn: () => apiClient.tunnel.getStatus(),
    refetchInterval: 5000, // Poll every 5 seconds
  });

  const status = statusQuery.data;

  // Start tunnel mutation
  const startMutation = useMutation({
    mutationFn: (token?: string) => apiClient.tunnel.start(token),
    onSuccess: (response) => {
      if (response.success) {
        toast.success('Tunnel started', {
          description: response.message,
        });
        setTokenInput(''); // Clear token input after successful start
      } else {
        toast.error('Failed to start tunnel', {
          description: response.message,
        });
      }
      queryClient.invalidateQueries({ queryKey: ['tunnel-status'] });
    },
    onError: (error: Error) => {
      toast.error('Failed to start tunnel', {
        description: error.message,
      });
    },
  });

  // Stop tunnel mutation
  const stopMutation = useMutation({
    mutationFn: () => apiClient.tunnel.stop(),
    onSuccess: (response) => {
      if (response.success) {
        toast.success('Tunnel stopped', {
          description: response.message,
        });
      } else {
        toast.error('Failed to stop tunnel', {
          description: response.message,
        });
      }
      queryClient.invalidateQueries({ queryKey: ['tunnel-status'] });
    },
    onError: (error: Error) => {
      toast.error('Failed to stop tunnel', {
        description: error.message,
      });
    },
  });

  // Handle toggle
  const handleToggle = async (enabled: boolean) => {
    if (enabled) {
      // If we have a token input, use it; otherwise start with stored token
      startMutation.mutate(tokenInput || undefined);
    } else {
      stopMutation.mutate();
    }
  };

  // Test connection handler (Story P13-2.4)
  const handleTestConnection = async () => {
    setIsTesting(true);
    try {
      // If token is provided, use dedicated test endpoint (doesn't persist config)
      if (tokenInput) {
        const result = await apiClient.tunnel.test(tokenInput);
        if (result.success) {
          toast.success('Connection test successful', {
            description: `Connected to ${result.hostname} in ${result.latency_ms}ms`,
          });
        } else {
          toast.error('Connection test failed', {
            description: result.error || 'Unknown error',
          });
        }
      } else {
        // No token provided - start with saved token
        const result = await apiClient.tunnel.start();
        if (result.success) {
          toast.success('Connection test successful', {
            description: result.message,
          });
        } else {
          toast.error('Connection test failed', {
            description: result.message,
          });
        }
      }
      queryClient.invalidateQueries({ queryKey: ['tunnel-status'] });
    } catch (error) {
      toast.error('Connection test failed', {
        description: error instanceof Error ? error.message : 'Unknown error',
      });
    } finally {
      setIsTesting(false);
    }
  };

  // Status badge component
  const getStatusBadge = () => {
    if (statusQuery.isLoading) {
      return (
        <Badge variant="secondary">
          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
          Loading...
        </Badge>
      );
    }

    if (!status) {
      return (
        <Badge variant="secondary">
          <CloudOff className="mr-1 h-3 w-3" />
          Unknown
        </Badge>
      );
    }

    switch (status.status) {
      case 'connected':
        return (
          <Badge variant="default" className="bg-green-600">
            <CheckCircle2 className="mr-1 h-3 w-3" />
            Connected
          </Badge>
        );
      case 'connecting':
        return (
          <Badge variant="default" className="bg-yellow-500">
            <Loader2 className="mr-1 h-3 w-3 animate-spin" />
            Connecting
          </Badge>
        );
      case 'error':
        return (
          <Badge variant="destructive">
            <AlertTriangle className="mr-1 h-3 w-3" />
            Error
          </Badge>
        );
      default:
        return (
          <Badge variant="secondary">
            <CloudOff className="mr-1 h-3 w-3" />
            Disconnected
          </Badge>
        );
    }
  };

  if (statusQuery.isLoading && !status) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  const isEnabled = status?.enabled || status?.is_running;
  const isPending = startMutation.isPending || stopMutation.isPending;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2">
              <Cloud className="h-5 w-5" />
              Cloudflare Tunnel
            </CardTitle>
            <CardDescription>
              Secure remote access without port forwarding
            </CardDescription>
          </div>
          {getStatusBadge()}
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Enable Toggle */}
        <div className="flex items-center justify-between rounded-lg border p-4">
          <div className="space-y-0.5">
            <Label htmlFor="tunnel-enabled" className="text-base font-medium">
              Enable Tunnel
            </Label>
            <p className="text-sm text-muted-foreground">
              Connect ArgusAI to your Cloudflare Tunnel for remote access
            </p>
          </div>
          <Switch
            id="tunnel-enabled"
            checked={isEnabled}
            onCheckedChange={handleToggle}
            disabled={isPending}
          />
        </div>

        {/* Token Input */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="tunnel-token">Tunnel Token</Label>
            {status?.hostname && (
              <Badge variant="outline" className="text-xs">
                <CheckCircle2 className="mr-1 h-3 w-3" />
                Token configured
              </Badge>
            )}
          </div>
          <div className="relative">
            <Input
              id="tunnel-token"
              type={showToken ? 'text' : 'password'}
              placeholder={status?.hostname ? '••••••••••••••••' : 'Enter Cloudflare Tunnel token'}
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              className="pr-10"
            />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
              onClick={() => setShowToken(!showToken)}
            >
              {showToken ? (
                <EyeOff className="h-4 w-4 text-muted-foreground" />
              ) : (
                <Eye className="h-4 w-4 text-muted-foreground" />
              )}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Get your token from the Cloudflare Zero Trust dashboard. Leave empty to use stored token.
          </p>
        </div>

        {/* Test Connection Button */}
        <Button
          type="button"
          variant="outline"
          onClick={handleTestConnection}
          disabled={isTesting || isPending}
          className="w-full"
        >
          {isTesting ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Testing connection...
            </>
          ) : (
            <>
              <RefreshCw className="mr-2 h-4 w-4" />
              Test Connection
            </>
          )}
        </Button>

        {/* Connected Status Details */}
        {status?.is_connected && (
          <div className="rounded-lg bg-muted/50 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Cloud className="h-4 w-4 text-green-600" />
              <span className="font-medium text-green-600">Tunnel Connected</span>
            </div>

            {/* Hostname */}
            {status.hostname && (
              <div className="flex items-center gap-2 text-sm">
                <ExternalLink className="h-4 w-4 text-muted-foreground" />
                <a
                  href={`https://${status.hostname}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline"
                >
                  {status.hostname}
                </a>
              </div>
            )}

            {/* Stats Grid */}
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-muted-foreground" />
                <div>
                  <span className="text-muted-foreground">Uptime:</span>
                  <span className="ml-1 font-medium">{formatUptime(status.uptime_seconds)}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-muted-foreground" />
                <div>
                  <span className="text-muted-foreground">Last:</span>
                  <span className="ml-1 font-medium">{formatLastConnected(status.last_connected)}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <RefreshCw className="h-4 w-4 text-muted-foreground" />
                <div>
                  <span className="text-muted-foreground">Reconnects:</span>
                  <span className="ml-1 font-medium">{status.reconnect_count}</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Error Display */}
        {status?.status === 'error' && status.error && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{status.error}</AlertDescription>
          </Alert>
        )}

        {/* Info when disabled */}
        {!isEnabled && !status?.is_connected && (
          <Alert>
            <Cloud className="h-4 w-4" />
            <AlertDescription>
              Enable Cloudflare Tunnel to access ArgusAI from anywhere without port forwarding.
              You&apos;ll need a Cloudflare account and a tunnel token from the Zero Trust dashboard.
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}
