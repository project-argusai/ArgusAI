'use client';

/**
 * WebhookLogs component - Story 5.3
 * Displays webhook delivery logs with filtering, pagination, and export
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { formatDistanceToNow, format } from 'date-fns';
import {
  Download,
  RefreshCw,
  CheckCircle,
  XCircle,
  Filter,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Clock,
  RotateCcw,
} from 'lucide-react';
import { toast } from 'sonner';

import { apiClient, ApiError } from '@/lib/api-client';
import type { IWebhookLog, IWebhookLogsFilter, IAlertRule } from '@/types/alert-rule';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const PAGE_SIZE = 20;

interface WebhookLogsProps {
  /** Optional rule ID to filter logs for a specific rule */
  ruleId?: string;
  /** Optional: compact mode with fewer columns */
  compact?: boolean;
}

export function WebhookLogs({ ruleId, compact = false }: WebhookLogsProps) {
  // Filter state
  const [filters, setFilters] = useState<IWebhookLogsFilter>({
    rule_id: ruleId,
    limit: PAGE_SIZE,
    offset: 0,
  });
  const [selectedLog, setSelectedLog] = useState<IWebhookLog | null>(null);

  // Fetch webhook logs
  const {
    data: logsResponse,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['webhookLogs', filters],
    queryFn: () => apiClient.webhooks.getLogs(filters),
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  // Fetch rules for filter dropdown (only if not filtering by specific rule)
  const { data: rulesResponse } = useQuery({
    queryKey: ['alertRules'],
    queryFn: () => apiClient.alertRules.list(),
    enabled: !ruleId, // Only fetch if not already filtering by rule
  });

  const logs = logsResponse?.data || [];
  const totalCount = logsResponse?.total_count || 0;
  const rules = rulesResponse?.data || [];

  // Pagination
  const currentPage = Math.floor((filters.offset || 0) / PAGE_SIZE) + 1;
  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  const handlePageChange = (page: number) => {
    setFilters(prev => ({
      ...prev,
      offset: (page - 1) * PAGE_SIZE,
    }));
  };

  const handleFilterChange = (key: keyof IWebhookLogsFilter, value: string | boolean | undefined) => {
    setFilters(prev => ({
      ...prev,
      [key]: value,
      offset: 0, // Reset to first page when filter changes
    }));
  };

  const handleExport = async () => {
    try {
      const blob = await apiClient.webhooks.exportLogs({
        rule_id: filters.rule_id,
        success: filters.success,
        start_date: filters.start_date,
        end_date: filters.end_date,
      });

      // Create download link
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `webhook_logs_${format(new Date(), 'yyyyMMdd_HHmmss')}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      toast.success('Logs exported successfully');
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to export logs';
      toast.error(message);
    }
  };

  const clearFilters = () => {
    setFilters({
      rule_id: ruleId,
      limit: PAGE_SIZE,
      offset: 0,
    });
  };

  const hasActiveFilters = filters.success !== undefined ||
    filters.start_date ||
    filters.end_date ||
    (!ruleId && filters.rule_id);

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">Webhook Delivery Logs</CardTitle>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
            >
              <RefreshCw className={`h-4 w-4 mr-1 ${isFetching ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleExport}
              disabled={logs.length === 0}
            >
              <Download className="h-4 w-4 mr-1" />
              Export CSV
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Filters */}
        <div className="flex flex-wrap gap-3 items-end">
          {/* Rule filter (only show if not pre-filtered) */}
          {!ruleId && (
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Rule</Label>
              <Select
                value={filters.rule_id || 'all'}
                onValueChange={(value) =>
                  handleFilterChange('rule_id', value === 'all' ? undefined : value)
                }
              >
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="All rules" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All rules</SelectItem>
                  {rules.map((rule: IAlertRule) => (
                    <SelectItem key={rule.id} value={rule.id}>
                      {rule.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Success filter */}
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Status</Label>
            <Select
              value={filters.success === undefined ? 'all' : filters.success.toString()}
              onValueChange={(value) =>
                handleFilterChange('success', value === 'all' ? undefined : value === 'true')
              }
            >
              <SelectTrigger className="w-[130px]">
                <SelectValue placeholder="All" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="true">Success</SelectItem>
                <SelectItem value="false">Failed</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Date filters */}
          {!compact && (
            <>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">From</Label>
                <Input
                  type="date"
                  className="w-[150px]"
                  value={filters.start_date || ''}
                  onChange={(e) => handleFilterChange('start_date', e.target.value || undefined)}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">To</Label>
                <Input
                  type="date"
                  className="w-[150px]"
                  value={filters.end_date || ''}
                  onChange={(e) => handleFilterChange('end_date', e.target.value || undefined)}
                />
              </div>
            </>
          )}

          {/* Clear filters */}
          {hasActiveFilters && (
            <Button variant="ghost" size="sm" onClick={clearFilters}>
              <Filter className="h-4 w-4 mr-1" />
              Clear
            </Button>
          )}
        </div>

        {/* Loading state */}
        {isLoading && <WebhookLogsSkeleton />}

        {/* Error state */}
        {isError && (
          <div className="text-center py-8 text-destructive">
            <p className="font-medium">Error loading webhook logs</p>
            <p className="text-sm text-muted-foreground mt-1">
              {error instanceof ApiError ? error.message : 'Unknown error'}
            </p>
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !isError && logs.length === 0 && (
          <div className="text-center py-8 text-muted-foreground">
            <p>No webhook logs found</p>
            <p className="text-sm mt-1">
              Logs will appear here when webhooks are triggered
            </p>
          </div>
        )}

        {/* Logs table */}
        {!isLoading && !isError && logs.length > 0 && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-left p-3 font-medium">Time</th>
                    {!ruleId && !compact && (
                      <th className="text-left p-3 font-medium">Rule</th>
                    )}
                    <th className="text-left p-3 font-medium">Status</th>
                    <th className="text-left p-3 font-medium hidden md:table-cell">Response</th>
                    {!compact && (
                      <th className="text-left p-3 font-medium hidden lg:table-cell">URL</th>
                    )}
                    <th className="text-right p-3 font-medium">Details</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log: IWebhookLog) => (
                    <WebhookLogRow
                      key={log.id}
                      log={log}
                      showRule={!ruleId && !compact}
                      compact={compact}
                      onClick={() => setSelectedLog(log)}
                    />
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between pt-2">
                <p className="text-sm text-muted-foreground">
                  Showing {((currentPage - 1) * PAGE_SIZE) + 1} - {Math.min(currentPage * PAGE_SIZE, totalCount)} of {totalCount}
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handlePageChange(currentPage - 1)}
                    disabled={currentPage === 1}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <span className="text-sm">
                    Page {currentPage} of {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handlePageChange(currentPage + 1)}
                    disabled={currentPage >= totalPages}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>

      {/* Log Detail Modal */}
      <WebhookLogDetailDialog
        log={selectedLog}
        open={!!selectedLog}
        onClose={() => setSelectedLog(null)}
      />
    </Card>
  );
}

interface WebhookLogRowProps {
  log: IWebhookLog;
  showRule: boolean;
  compact: boolean;
  onClick: () => void;
}

function WebhookLogRow({ log, showRule, compact, onClick }: WebhookLogRowProps) {
  const timeAgo = formatDistanceToNow(new Date(log.created_at), { addSuffix: true });

  return (
    <tr
      className="border-b hover:bg-muted/50 transition-colors cursor-pointer"
      onClick={onClick}
    >
      {/* Time */}
      <td className="p-3">
        <div className="text-sm">{timeAgo}</div>
        <div className="text-xs text-muted-foreground">
          {format(new Date(log.created_at), 'HH:mm:ss')}
        </div>
      </td>

      {/* Rule (optional) */}
      {showRule && (
        <td className="p-3">
          <span className="text-sm">{log.rule_name || 'Unknown'}</span>
        </td>
      )}

      {/* Status */}
      <td className="p-3">
        <div className="flex items-center gap-2">
          {log.success ? (
            <Badge variant="default" className="bg-green-500 hover:bg-green-600">
              <CheckCircle className="h-3 w-3 mr-1" />
              {log.status_code}
            </Badge>
          ) : (
            <Badge variant="destructive">
              <XCircle className="h-3 w-3 mr-1" />
              {log.status_code || 'Error'}
            </Badge>
          )}
          {log.retry_count > 0 && (
            <Badge variant="outline" className="text-xs">
              <RotateCcw className="h-3 w-3 mr-1" />
              {log.retry_count}
            </Badge>
          )}
        </div>
      </td>

      {/* Response time */}
      <td className="p-3 hidden md:table-cell">
        <div className="flex items-center text-sm text-muted-foreground">
          <Clock className="h-3 w-3 mr-1" />
          {log.response_time_ms}ms
        </div>
      </td>

      {/* URL (truncated) */}
      {!compact && (
        <td className="p-3 hidden lg:table-cell">
          <span className="text-sm text-muted-foreground truncate block max-w-[200px]" title={log.url}>
            {log.url}
          </span>
        </td>
      )}

      {/* View details */}
      <td className="p-3 text-right">
        <Button variant="ghost" size="sm">
          <ExternalLink className="h-4 w-4" />
        </Button>
      </td>
    </tr>
  );
}

interface WebhookLogDetailDialogProps {
  log: IWebhookLog | null;
  open: boolean;
  onClose: () => void;
}

function WebhookLogDetailDialog({ log, open, onClose }: WebhookLogDetailDialogProps) {
  if (!log) return null;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Webhook Delivery Details</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Status */}
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">Status</span>
            {log.success ? (
              <Badge variant="default" className="bg-green-500">
                <CheckCircle className="h-3 w-3 mr-1" />
                Success
              </Badge>
            ) : (
              <Badge variant="destructive">
                <XCircle className="h-3 w-3 mr-1" />
                Failed
              </Badge>
            )}
          </div>

          {/* Timestamp */}
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">Timestamp</span>
            <span className="text-sm text-muted-foreground">
              {format(new Date(log.created_at), 'PPpp')}
            </span>
          </div>

          {/* Rule */}
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">Rule</span>
            <span className="text-sm text-muted-foreground">
              {log.rule_name || log.alert_rule_id}
            </span>
          </div>

          {/* Event ID */}
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">Event ID</span>
            <span className="text-sm text-muted-foreground font-mono truncate max-w-[200px]" title={log.event_id}>
              {log.event_id}
            </span>
          </div>

          {/* URL */}
          <div>
            <span className="text-sm font-medium">URL</span>
            <p className="text-sm text-muted-foreground break-all mt-1 font-mono bg-muted p-2 rounded">
              {log.url}
            </p>
          </div>

          {/* Response Details */}
          <div className="grid grid-cols-3 gap-4">
            <div>
              <span className="text-sm font-medium">Status Code</span>
              <p className="text-sm text-muted-foreground">{log.status_code}</p>
            </div>
            <div>
              <span className="text-sm font-medium">Response Time</span>
              <p className="text-sm text-muted-foreground">{log.response_time_ms}ms</p>
            </div>
            <div>
              <span className="text-sm font-medium">Retries</span>
              <p className="text-sm text-muted-foreground">{log.retry_count}</p>
            </div>
          </div>

          {/* Error message (if any) */}
          {log.error_message && (
            <div>
              <span className="text-sm font-medium">Error</span>
              <p className="text-sm text-destructive break-all mt-1 bg-destructive/10 p-2 rounded">
                {log.error_message}
              </p>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function WebhookLogsSkeleton() {
  return (
    <div className="space-y-2">
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="flex items-center gap-4 p-3">
          <Skeleton className="h-8 w-24" />
          <Skeleton className="h-6 w-20" />
          <Skeleton className="h-6 w-16 hidden md:block" />
          <Skeleton className="h-6 w-32 hidden lg:block" />
          <div className="flex-1" />
          <Skeleton className="h-8 w-8" />
        </div>
      ))}
    </div>
  );
}
