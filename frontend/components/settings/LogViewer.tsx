/**
 * LogViewer component - displays application logs with filtering
 * FF-001: Log Viewer UI for troubleshooting
 */

'use client';

import { useState, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { format } from 'date-fns';
import {
  Search,
  Download,
  RefreshCw,
  AlertCircle,
  AlertTriangle,
  Info,
  Bug,
  ChevronDown,
  ChevronUp,
  Loader2,
} from 'lucide-react';
import { apiClient } from '@/lib/api-client';
import type { LogEntry, LogsQueryParams } from '@/types/monitoring';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

const LOG_LEVELS = ['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] as const;
type LogLevel = typeof LOG_LEVELS[number];

const LEVEL_CONFIG: Record<string, { icon: typeof Info; color: string; bgColor: string }> = {
  DEBUG: { icon: Bug, color: 'text-gray-500', bgColor: 'bg-gray-100' },
  INFO: { icon: Info, color: 'text-blue-500', bgColor: 'bg-blue-100' },
  WARNING: { icon: AlertTriangle, color: 'text-yellow-600', bgColor: 'bg-yellow-100' },
  ERROR: { icon: AlertCircle, color: 'text-red-500', bgColor: 'bg-red-100' },
  CRITICAL: { icon: AlertCircle, color: 'text-red-700', bgColor: 'bg-red-200' },
};

interface LogEntryRowProps {
  entry: LogEntry;
  isExpanded: boolean;
  onToggle: () => void;
}

function LogEntryRow({ entry, isExpanded, onToggle }: LogEntryRowProps) {
  const config = LEVEL_CONFIG[entry.level] || LEVEL_CONFIG.INFO;
  const Icon = config.icon;

  // Safely parse timestamp - handle invalid or malformed values
  let timestamp = '--';
  if (entry.timestamp) {
    try {
      const date = new Date(entry.timestamp);
      // Check if date is valid (Invalid Date has NaN for getTime())
      if (!isNaN(date.getTime())) {
        timestamp = format(date, 'HH:mm:ss.SSS');
      }
    } catch {
      // Keep default '--' on parse error
    }
  }
  const hasExtra = entry.extra && Object.keys(entry.extra).length > 0;

  return (
    <div className="border-b last:border-b-0">
      <div
        className={cn(
          'flex items-start gap-2 p-2 cursor-pointer hover:bg-muted/50 transition-colors',
          isExpanded && 'bg-muted/30'
        )}
        onClick={onToggle}
      >
        <Icon className={cn('w-4 h-4 mt-0.5 flex-shrink-0', config.color)} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Badge variant="outline" className={cn('text-xs px-1.5 py-0', config.bgColor, config.color)}>
              {entry.level}
            </Badge>
            <span className="text-xs text-muted-foreground font-mono">{timestamp}</span>
            {entry.module && (
              <span className="text-xs text-muted-foreground truncate">{entry.module}</span>
            )}
          </div>
          <p className={cn('text-sm break-words', isExpanded ? '' : 'line-clamp-2')}>
            {entry.message}
          </p>
        </div>
        {(hasExtra || entry.function) && (
          <Button variant="ghost" size="sm" className="h-6 w-6 p-0 flex-shrink-0">
            {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </Button>
        )}
      </div>

      {isExpanded && (hasExtra || entry.function) && (
        <div className="px-8 pb-2 text-xs space-y-1 bg-muted/20">
          {entry.function && (
            <div className="font-mono text-muted-foreground">
              {entry.function}:{entry.line}
            </div>
          )}
          {entry.request_id && (
            <div className="text-muted-foreground">
              Request ID: <span className="font-mono">{entry.request_id}</span>
            </div>
          )}
          {hasExtra && (
            <pre className="mt-2 p-2 bg-muted rounded text-xs overflow-x-auto">
              {JSON.stringify(entry.extra, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

export function LogViewer() {
  const [level, setLevel] = useState<LogLevel>('ALL');
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [isDownloading, setIsDownloading] = useState(false);

  const queryParams: LogsQueryParams = {
    level: level === 'ALL' ? undefined : level,
    search: search || undefined,
    limit: 200,
  };

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['logs', queryParams],
    queryFn: () => apiClient.monitoring.getLogs(queryParams),
    refetchInterval: 30000, // Auto-refresh every 30 seconds
  });

  const handleSearch = useCallback(() => {
    setSearch(searchInput);
  }, [searchInput]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  }, [handleSearch]);

  const toggleExpanded = useCallback((index: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  }, []);

  const handleDownload = useCallback(async () => {
    setIsDownloading(true);
    try {
      const blob = await apiClient.monitoring.downloadLogs(undefined, 'app');
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `logs-${format(new Date(), 'yyyy-MM-dd-HHmmss')}.log`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      toast.success('Logs downloaded successfully');
    } catch (err) {
      toast.error('Failed to download logs');
      console.error('Download error:', err);
    } finally {
      setIsDownloading(false);
    }
  }, []);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Application Logs</CardTitle>
            <CardDescription>
              View and search application logs for troubleshooting
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
            >
              <RefreshCw className={cn('w-4 h-4 mr-2', isFetching && 'animate-spin')} />
              Refresh
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownload}
              disabled={isDownloading}
            >
              {isDownloading ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Download className="w-4 h-4 mr-2" />
              )}
              Download
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Filters */}
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="flex-1">
            <Label htmlFor="log-search" className="sr-only">Search logs</Label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                id="log-search"
                placeholder="Search log messages..."
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={handleKeyDown}
                className="pl-10"
              />
            </div>
          </div>
          <div className="w-full sm:w-40">
            <Label htmlFor="log-level" className="sr-only">Log level</Label>
            <Select value={level} onValueChange={(v) => setLevel(v as LogLevel)}>
              <SelectTrigger id="log-level">
                <SelectValue placeholder="Log level" />
              </SelectTrigger>
              <SelectContent>
                {LOG_LEVELS.map((l) => (
                  <SelectItem key={l} value={l}>
                    {l === 'ALL' ? 'All Levels' : l}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button onClick={handleSearch} className="sm:w-auto">
            <Search className="w-4 h-4 mr-2" />
            Search
          </Button>
        </div>

        {/* Results summary */}
        {data && (
          <div className="text-sm text-muted-foreground">
            Showing {data.entries.length} of {data.total} log entries
            {data.has_more && ' (scroll for more)'}
          </div>
        )}

        {/* Log entries */}
        <div className="border rounded-lg max-h-[600px] overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
              <span className="ml-2 text-muted-foreground">Loading logs...</span>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <AlertCircle className="w-8 h-8 text-red-500 mb-2" />
              <p className="text-sm text-muted-foreground">Failed to load logs</p>
              <Button variant="outline" size="sm" className="mt-2" onClick={() => refetch()}>
                Retry
              </Button>
            </div>
          ) : data?.entries.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <Info className="w-8 h-8 text-muted-foreground mb-2" />
              <p className="text-sm text-muted-foreground">No log entries found</p>
              {(search || level !== 'ALL') && (
                <p className="text-xs text-muted-foreground mt-1">
                  Try adjusting your filters
                </p>
              )}
            </div>
          ) : (
            data?.entries.map((entry, index) => (
              <LogEntryRow
                key={`${entry.timestamp}-${index}`}
                entry={entry}
                isExpanded={expandedIds.has(index)}
                onToggle={() => toggleExpanded(index)}
              />
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}
