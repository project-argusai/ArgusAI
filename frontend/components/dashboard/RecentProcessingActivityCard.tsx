'use client';

import { useState, useEffect, useRef, useMemo } from 'react';
import Link from 'next/link';
import { apiClient } from '@/lib/api-client';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { RefreshCw, Clock, AlertTriangle, CheckCircle2, Pause, XCircle, ArrowRight } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

interface RecentProcessingActivityCardProps {
  title?: string;
  variant?: 'full' | 'mini';
  limit?: number;
}

export function RecentProcessingActivityCard({
  title = 'Recent AI Processing Activity',
  variant = 'full',
  limit = variant === 'mini' ? 8 : 20,
}: RecentProcessingActivityCardProps) {
  const [records, setRecords] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLiveConnected, setIsLiveConnected] = useState(false);

  // Compact summary stats for the mini variant
  const summary = useMemo(() => {
    if (!records.length) return null;

    let processed = 0;
    let skipped = 0;
    let errors = 0;

    records.forEach((r: any) => {
      if (r.analysis_skipped) {
        skipped++;
      } else if (r.success === false) {
        errors++;
      } else {
        processed++;
      }
    });

    return {
      total: records.length,
      processed,
      skipped,
      errors,
    };
  }, [records]);

  // Time span of the current buffer (for mini variant)
  const timeSpan = useMemo(() => {
    if (records.length < 2) return null;

    const timestamps = records
      .map((r: any) => r.timestamp)
      .filter((t: number) => typeof t === 'number');

    if (timestamps.length < 2) return null;

    const oldest = Math.min(...timestamps);
    const newest = Math.max(...timestamps);
    const diff = newest - oldest; // seconds

    if (diff < 60) return `${diff}s span`;
    if (diff < 3600) return `${Math.round(diff / 60)}m span`;
    return `${(diff / 3600).toFixed(1)}h span`;
  }, [records]);

  const eventSourceRef = useRef<EventSource | null>(null);

  const fetchData = async (reset = true) => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await apiClient.getAIProcessingRecent({ limit });
      const newRecords = res?.recent_activity || [];
      if (reset) {
        setRecords(newRecords);
      } else {
        // Merge without duplicates (simple approach for manual refresh)
        const existingIds = new Set(records.map((r: any) => r.timestamp + r.camera_id));
        const merged = [...newRecords.filter((r: any) => !existingIds.has(r.timestamp + r.camera_id)), ...records];
        setRecords(merged.slice(0, limit));
      }
    } catch (err) {
      console.error('Failed to load recent processing activity:', err);
      setError('Unable to load recent AI processing activity.');
      if (reset) setRecords([]);
    } finally {
      setIsLoading(false);
    }
  };

  // Live updates via SSE
  const connectLive = () => {
    if (eventSourceRef.current) return;

    try {
      const es = new EventSource('/api/v1/system/ai-processing-stream');
      eventSourceRef.current = es;

      es.onopen = () => {
        setIsLiveConnected(true);
      };

      es.onmessage = (event) => {
        try {
          const record = JSON.parse(event.data);
          if (record && record.camera_id) {
            setRecords((prev) => {
              // Avoid immediate duplicates
              if (prev.some((r) => r.timestamp === record.timestamp && r.camera_id === record.camera_id)) {
                return prev;
              }
              const updated = [record, ...prev].slice(0, limit);
              return updated;
            });
          }
        } catch (e) {
          // ignore malformed messages
        }
      };

      es.onerror = () => {
        setIsLiveConnected(false);
        // Attempt to reconnect after a delay
        setTimeout(() => {
          if (eventSourceRef.current) {
            eventSourceRef.current.close();
            eventSourceRef.current = null;
          }
          connectLive();
        }, 3000);
      };
    } catch (e) {
      setIsLiveConnected(false);
    }
  };

  const disconnectLive = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsLiveConnected(false);
  };

  useEffect(() => {
    fetchData();

    // Start live updates
    connectLive();

    return () => {
      disconnectLive();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reconnect live stream if limit changes (rare)
  useEffect(() => {
    if (isLiveConnected) {
      disconnectLive();
      connectLive();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [limit]);

  const getStatusInfo = (record: any) => {
    if (record.analysis_skipped) {
      return {
        icon: <Pause className="h-4 w-4" />,
        label: 'Skipped',
        color: 'text-amber-600 bg-amber-100',
        detail: record.analysis_skipped_reason || 'cost cap',
      };
    }
    if (record.success === false) {
      return {
        icon: <XCircle className="h-4 w-4" />,
        label: 'Error',
        color: 'text-red-600 bg-red-100',
        detail: record.error ? record.error.substring(0, 60) : 'processing failed',
      };
    }
    return {
      icon: <CheckCircle2 className="h-4 w-4" />,
      label: 'Processed',
      color: 'text-emerald-600 bg-emerald-100',
      detail: record.provider || '—',
    };
  };

  const formatCost = (cost?: number) => {
    if (cost == null) return '';
    return `$${cost.toFixed(4)}`;
  };

  const formatLatency = (ms?: number) => {
    if (ms == null) return '';
    return `${Math.round(ms)}ms`;
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <div>
          <CardTitle className="text-base flex items-center gap-2">
            <Clock className="h-5 w-5" />
            {title}
          </CardTitle>
          {variant === 'mini' && summary && (
            <>
              <div className="text-[11px] text-muted-foreground mt-0.5 font-mono tabular-nums tracking-tight">
                {summary.processed} processed • {summary.skipped} skipped • {summary.errors} error{summary.errors === 1 ? '' : 's'}
              </div>
              {timeSpan && (
                <div className="text-[10px] text-muted-foreground/70 mt-px font-mono">
                  Last {summary.total} events • {timeSpan}
                </div>
              )}
            </>
          )}
          {variant === 'mini' && !summary && (
            <CardDescription className="text-xs">
              Live ring buffer
            </CardDescription>
          )}
        </div>

        <div className="flex items-center gap-2">
          {isLiveConnected && (
            <span className="flex items-center gap-1 text-xs text-emerald-600 font-medium">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              Live
            </span>
          )}

          {variant === 'mini' && (
            <Link
              href="/status"
              className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
            >
              View full details
              <ArrowRight className="h-3 w-3" />
            </Link>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchData()}
            disabled={isLoading}
          >
            <RefreshCw className={`h-4 w-4 mr-1 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </CardHeader>

      <CardContent>
        {/* Error State */}
        {error && !isLoading && (
          <div className="flex flex-col items-center justify-center py-6 text-center">
            <AlertTriangle className="h-5 w-5 text-muted-foreground mb-2" />
            <div className="text-sm text-muted-foreground mb-3">{error}</div>
            <Button variant="outline" size="sm" onClick={() => fetchData(true)}>
              <RefreshCw className="h-4 w-4 mr-1.5" />
              Try again
            </Button>
          </div>
        )}

        {/* Loading State (initial) */}
        {!error && isLoading && records.length === 0 && (
          <div className="flex items-center justify-center py-6">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <RefreshCw className="h-4 w-4 animate-spin" />
              Loading recent AI activity...
            </div>
          </div>
        )}

        {/* Empty State */}
        {!error && !isLoading && records.length === 0 && (
          <div className="flex flex-col items-center justify-center py-6 text-center">
            <Clock className="h-5 w-5 text-muted-foreground mb-2" />
            <div className="text-sm text-muted-foreground mb-1">
              No recent AI processing activity yet.
            </div>
            <div className="text-xs text-muted-foreground">
              Once the coordinator processes events, they will appear here in real time.
            </div>
          </div>
        )}

        {/* Main List */}
        {!error && records.length > 0 && (
          <div className="space-y-2">
            {records.map((record: any) => {
              const status = getStatusInfo(record);
              const time = record.timestamp
                ? formatDistanceToNow(new Date(record.timestamp * 1000), { addSuffix: true })
                : '';

              const entityInfo =
                record.entity_final?.entity_name ||
                record.entity_early?.entity_name ||
                (record.entity_final?.is_new || record.entity_early?.is_new ? 'New entity' : null);

              const key = `${record.timestamp}-${record.camera_id}`;

              return (
                <div
                  key={key}
                  className="flex flex-col sm:flex-row sm:items-center gap-2 border rounded-md p-3 text-sm hover:bg-muted/50 transition"
                >
                  {/* Time + Camera */}
                  <div className="flex-shrink-0 w-full sm:w-48">
                    <div className="font-mono text-xs text-muted-foreground">{time}</div>
                    <div className="font-medium truncate">{record.camera_id}</div>
                  </div>

                  {/* Status */}
                  <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium ${status.color} flex-shrink-0`}>
                    {status.icon}
                    <span>{status.label}</span>
                  </div>

                  {/* AI Signal */}
                  <div className="flex-1 min-w-0 text-muted-foreground text-xs sm:text-sm">
                    {record.analysis_skipped ? (
                      <span className="text-amber-600">Skipped: {status.detail}</span>
                    ) : record.success === false ? (
                      <span className="text-red-600 truncate">{status.detail}</span>
                    ) : (
                      <span>
                        {record.provider} · {formatCost(record.ai_cost)} · {formatLatency(record.ai_response_time_ms)}
                      </span>
                    )}
                  </div>

                  {/* Description / Entity */}
                  <div className="flex-1 min-w-0 text-sm truncate">
                    {record.description ? (
                      record.description.length > 80 ? record.description.substring(0, 77) + '...' : record.description
                    ) : entityInfo ? (
                      <span className="text-muted-foreground">Entity: {entityInfo}</span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </div>

                  {/* Flags (only in full variant) */}
                  {variant === 'full' && (
                    <div className="flex gap-1 text-[10px] flex-shrink-0">
                      {record.regenerated && <span className="px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded">regen</span>}
                      {record.low_confidence && <span className="px-1.5 py-0.5 bg-red-100 text-red-700 rounded">low conf</span>}
                      {record.ocr_used && <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded">ocr</span>}
                      {(record.entity_final?.is_new || record.entity_early?.is_new) && (
                        <span className="px-1.5 py-0.5 bg-emerald-100 text-emerald-700 rounded">new</span>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
