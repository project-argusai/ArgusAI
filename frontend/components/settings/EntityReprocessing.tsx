/**
 * EntityReprocessing component (Epic P13-3)
 *
 * Settings UI for bulk entity reprocessing with:
 * - Filter options (date range, camera, only unmatched)
 * - Event count estimate
 * - Start/cancel controls
 * - Real-time progress via WebSocket
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  RefreshCw,
  Loader2,
  Play,
  Square,
  CheckCircle2,
  AlertTriangle,
  Users,
  Calendar,
  Camera,
  Filter,
  TrendingUp,
} from 'lucide-react';

import {
  apiClient,
  type ReprocessingJob,
  type ReprocessingFilters,
} from '@/lib/api-client';
import { useWebSocket } from '@/hooks/useWebSocket';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

/**
 * Format seconds to human-readable duration
 */
function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${mins}m ${secs}s`;
  }
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${mins}m`;
}

export function EntityReprocessing() {
  const queryClient = useQueryClient();
  const { lastMessage } = useWebSocket();

  // Filter state
  const [filters, setFilters] = useState<ReprocessingFilters>({
    only_unmatched: true,
  });
  const [dateRange, setDateRange] = useState<'all' | '7d' | '30d' | '90d'>('all');

  // Local job state (updated via WebSocket)
  const [liveJob, setLiveJob] = useState<ReprocessingJob | null>(null);

  // Fetch cameras for filter
  const camerasQuery = useQuery({
    queryKey: ['cameras'],
    queryFn: () => apiClient.getCameras(),
  });

  // Fetch current job status
  const statusQuery = useQuery({
    queryKey: ['reprocessing-status'],
    queryFn: () => apiClient.reprocessing.getStatus(),
    refetchInterval: liveJob?.status === 'running' ? 5000 : false,
  });

  // Fetch estimate when filters change
  const estimateQuery = useQuery({
    queryKey: ['reprocessing-estimate', filters],
    queryFn: () => apiClient.reprocessing.estimate(filters),
    enabled: !liveJob || liveJob.status !== 'running',
  });

  // Update liveJob when statusQuery updates
  useEffect(() => {
    if (statusQuery.data) {
      setLiveJob(statusQuery.data);
    }
  }, [statusQuery.data]);

  // Handle WebSocket messages for real-time progress
  useEffect(() => {
    if (!lastMessage) return;

    try {
      const message = JSON.parse(lastMessage);

      if (message.type === 'reprocessing_progress' && liveJob) {
        setLiveJob((prev) => {
          if (!prev || prev.job_id !== message.data.job_id) return prev;
          return {
            ...prev,
            processed: message.data.processed,
            matched: message.data.matched,
            embeddings_generated: message.data.embeddings_generated,
            errors: message.data.errors,
            percent_complete: message.data.percent_complete,
          };
        });
      } else if (message.type === 'reprocessing_complete') {
        // Refetch status to get final state
        queryClient.invalidateQueries({ queryKey: ['reprocessing-status'] });
        queryClient.invalidateQueries({ queryKey: ['reprocessing-estimate'] });

        if (message.data.status === 'completed') {
          toast.success('Reprocessing Complete', {
            description: `Matched ${message.data.total_matched} entities in ${formatDuration(message.data.duration_seconds)}`,
          });
        } else if (message.data.status === 'cancelled') {
          toast.info('Reprocessing Cancelled', {
            description: `Processed ${message.data.total_processed} events before cancellation`,
          });
        } else if (message.data.status === 'failed') {
          toast.error('Reprocessing Failed', {
            description: message.data.error_message || 'Unknown error',
          });
        }
      }
    } catch {
      // Ignore non-JSON messages
    }
  }, [lastMessage, liveJob, queryClient]);

  // Start reprocessing mutation
  const startMutation = useMutation({
    mutationFn: () => apiClient.reprocessing.start(filters),
    onSuccess: (job) => {
      setLiveJob(job);
      toast.success('Reprocessing Started', {
        description: `Processing ${job.total_events} events`,
      });
      queryClient.invalidateQueries({ queryKey: ['reprocessing-status'] });
    },
    onError: (error: Error) => {
      toast.error('Failed to Start Reprocessing', {
        description: error.message,
      });
    },
  });

  // Cancel reprocessing mutation
  const cancelMutation = useMutation({
    mutationFn: () => apiClient.reprocessing.cancel(),
    onSuccess: (job) => {
      setLiveJob(job);
      queryClient.invalidateQueries({ queryKey: ['reprocessing-status'] });
    },
    onError: (error: Error) => {
      toast.error('Failed to Cancel', {
        description: error.message,
      });
    },
  });

  // Handle date range change
  const handleDateRangeChange = useCallback((value: string) => {
    setDateRange(value as typeof dateRange);

    if (value === 'all') {
      setFilters((prev) => ({
        ...prev,
        start_date: undefined,
        end_date: undefined,
      }));
    } else {
      const days = parseInt(value);
      const endDate = new Date();
      const startDate = new Date();
      startDate.setDate(startDate.getDate() - days);

      setFilters((prev) => ({
        ...prev,
        start_date: startDate.toISOString(),
        end_date: endDate.toISOString(),
      }));
    }
  }, []);

  const isRunning = liveJob?.status === 'running';
  const isPending = startMutation.isPending || cancelMutation.isPending;

  // Get status badge
  const getStatusBadge = () => {
    if (!liveJob) return null;

    switch (liveJob.status) {
      case 'running':
        return (
          <Badge variant="default" className="bg-blue-600">
            <Loader2 className="mr-1 h-3 w-3 animate-spin" />
            Running
          </Badge>
        );
      case 'completed':
        return (
          <Badge variant="default" className="bg-green-600">
            <CheckCircle2 className="mr-1 h-3 w-3" />
            Completed
          </Badge>
        );
      case 'cancelled':
        return (
          <Badge variant="secondary">
            <Square className="mr-1 h-3 w-3" />
            Cancelled
          </Badge>
        );
      case 'failed':
        return (
          <Badge variant="destructive">
            <AlertTriangle className="mr-1 h-3 w-3" />
            Failed
          </Badge>
        );
      default:
        return null;
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2">
              <RefreshCw className="h-5 w-5" />
              Entity Reprocessing
            </CardTitle>
            <CardDescription>
              Reprocess historical events for improved entity matching
            </CardDescription>
          </div>
          {getStatusBadge()}
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Filters */}
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Filter className="h-4 w-4" />
            Filters
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            {/* Date Range */}
            <div className="space-y-2">
              <Label htmlFor="date-range" className="flex items-center gap-2">
                <Calendar className="h-4 w-4 text-muted-foreground" />
                Date Range
              </Label>
              <Select
                value={dateRange}
                onValueChange={handleDateRangeChange}
                disabled={isRunning}
              >
                <SelectTrigger id="date-range">
                  <SelectValue placeholder="Select range" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Time</SelectItem>
                  <SelectItem value="7d">Last 7 Days</SelectItem>
                  <SelectItem value="30d">Last 30 Days</SelectItem>
                  <SelectItem value="90d">Last 90 Days</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Camera Filter */}
            <div className="space-y-2">
              <Label htmlFor="camera" className="flex items-center gap-2">
                <Camera className="h-4 w-4 text-muted-foreground" />
                Camera
              </Label>
              <Select
                value={filters.camera_id || 'all'}
                onValueChange={(value) =>
                  setFilters((prev) => ({
                    ...prev,
                    camera_id: value === 'all' ? undefined : value,
                  }))
                }
                disabled={isRunning}
              >
                <SelectTrigger id="camera">
                  <SelectValue placeholder="Select camera" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Cameras</SelectItem>
                  {camerasQuery.data?.map((camera) => (
                    <SelectItem key={camera.id} value={camera.id}>
                      {camera.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Only Unmatched Toggle */}
          <div className="flex items-center justify-between rounded-lg border p-4">
            <div className="space-y-0.5">
              <Label htmlFor="only-unmatched" className="text-base font-medium">
                Only Unmatched Events
              </Label>
              <p className="text-sm text-muted-foreground">
                Skip events that already have entity matches
              </p>
            </div>
            <Switch
              id="only-unmatched"
              checked={filters.only_unmatched}
              onCheckedChange={(checked) =>
                setFilters((prev) => ({ ...prev, only_unmatched: checked }))
              }
              disabled={isRunning}
            />
          </div>
        </div>

        {/* Estimate */}
        {!isRunning && estimateQuery.data && (
          <div className="rounded-lg bg-muted/50 p-4">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-muted-foreground" />
              <span className="font-medium">
                {estimateQuery.data.estimated_events.toLocaleString()} events
              </span>
              <span className="text-sm text-muted-foreground">
                will be processed
              </span>
            </div>
          </div>
        )}

        {/* Progress */}
        {isRunning && liveJob && (
          <div className="space-y-4 rounded-lg bg-muted/50 p-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Processing Events</span>
              <span className="text-sm text-muted-foreground">
                {liveJob.processed.toLocaleString()} / {liveJob.total_events.toLocaleString()}
              </span>
            </div>

            <Progress value={liveJob.percent_complete} className="h-2" />

            <div className="grid grid-cols-3 gap-4 text-center text-sm">
              <div>
                <div className="flex items-center justify-center gap-1 text-muted-foreground">
                  <Users className="h-4 w-4" />
                  Matched
                </div>
                <div className="font-semibold text-green-600">
                  {liveJob.matched.toLocaleString()}
                </div>
              </div>
              <div>
                <div className="flex items-center justify-center gap-1 text-muted-foreground">
                  <RefreshCw className="h-4 w-4" />
                  Embeddings
                </div>
                <div className="font-semibold">
                  {liveJob.embeddings_generated.toLocaleString()}
                </div>
              </div>
              <div>
                <div className="flex items-center justify-center gap-1 text-muted-foreground">
                  <AlertTriangle className="h-4 w-4" />
                  Errors
                </div>
                <div className="font-semibold text-red-600">
                  {liveJob.errors.toLocaleString()}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Completed Results */}
        {liveJob && liveJob.status === 'completed' && (
          <Alert>
            <CheckCircle2 className="h-4 w-4" />
            <AlertDescription>
              Completed processing {liveJob.processed.toLocaleString()} events.
              Matched {liveJob.matched.toLocaleString()} to entities.
              {liveJob.embeddings_generated > 0 && (
                <> Generated {liveJob.embeddings_generated.toLocaleString()} new embeddings.</>
              )}
            </AlertDescription>
          </Alert>
        )}

        {/* Error Display */}
        {liveJob?.status === 'failed' && liveJob.error_message && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{liveJob.error_message}</AlertDescription>
          </Alert>
        )}

        {/* Action Buttons */}
        <div className="flex gap-2">
          {!isRunning ? (
            <Button
              onClick={() => startMutation.mutate()}
              disabled={isPending || !estimateQuery.data || estimateQuery.data.estimated_events === 0}
              className="flex-1"
            >
              {startMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Starting...
                </>
              ) : (
                <>
                  <Play className="mr-2 h-4 w-4" />
                  Start Reprocessing
                </>
              )}
            </Button>
          ) : (
            <Button
              variant="destructive"
              onClick={() => cancelMutation.mutate()}
              disabled={isPending}
              className="flex-1"
            >
              {cancelMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Cancelling...
                </>
              ) : (
                <>
                  <Square className="mr-2 h-4 w-4" />
                  Cancel
                </>
              )}
            </Button>
          )}
        </div>

        {/* Info when no events */}
        {!isRunning && estimateQuery.data?.estimated_events === 0 && (
          <Alert>
            <Users className="h-4 w-4" />
            <AlertDescription>
              No events match the selected filters. Try adjusting the date range or disabling
              &quot;Only Unmatched Events&quot; to include already-matched events.
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}
