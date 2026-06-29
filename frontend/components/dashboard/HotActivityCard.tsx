'use client';

import { useState, useEffect, useMemo, useRef } from 'react';
import Link from 'next/link';
import { apiClient } from '@/lib/api-client';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  Flame,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Camera,
  Activity,
  ArrowRight,
} from 'lucide-react';
import type { HotActivityData, HotCamera, HotEntity } from '@/types/monitoring';

interface HotActivityCardProps {
  title?: string;
  storageKey?: string;
  defaultExpanded?: boolean;
  limit?: number;
  variant?: 'full' | 'mini';
}

export function HotActivityCard({
  title = 'Hot Activity (Trending)',
  storageKey = 'argusai_hot_activity_expanded',
  defaultExpanded = true,
  limit = 8,
  variant = 'full',
}: HotActivityCardProps) {
  // Data and filter state
  const [hotData, setHotData] = useState<HotActivityData | null>(null);
  const [hotMinScore, setHotMinScore] = useState<number | ''>('');
  const [hotMinCameraScore, setHotMinCameraScore] = useState<number | ''>('');
  const [hotOnlyNew, setHotOnlyNew] = useState<boolean>(false);
  const [isLoadingHot, setIsLoadingHot] = useState(false);

  // Collapsible state (persisted)
  const [isHotExpanded, setIsHotExpanded] = useState<boolean>(defaultExpanded);

  // In mini variant we always show the content (no collapse)
  const effectiveExpanded = variant === 'mini' ? true : isHotExpanded;

  // Use a smaller display limit in mini mode
  const displayLimit = variant === 'mini' ? Math.min(5, limit) : limit;

  // Live WebSocket connection state
  const [isLiveConnected, setIsLiveConnected] = useState(false);
  const hotWsRef = useRef<WebSocket | null>(null);

  // Load persisted expansion state
  useEffect(() => {
    const saved = localStorage.getItem(storageKey);
    if (saved !== null) {
      setIsHotExpanded(saved === 'true');
    }
  }, [storageKey]);

  // Persist expansion state
  useEffect(() => {
    localStorage.setItem(storageKey, String(isHotExpanded));
  }, [isHotExpanded, storageKey]);

  // Load hot data from coordinator
  const loadHotActivity = async () => {
    setIsLoadingHot(true);
    try {
      const params: NonNullable<Parameters<typeof apiClient.getAIProcessingHot>[0]> = { limit };
      if (hotMinScore !== '') params.min_score = Number(hotMinScore);
      if (hotMinCameraScore !== '') params.min_camera_score = Number(hotMinCameraScore);
      if (hotOnlyNew) params.entity_is_new = true;

      const data = await apiClient.getAIProcessingHot(params);
      setHotData(data);
    } catch (error) {
      console.error('Failed to load hot activity:', error);
      setHotData(null);
    } finally {
      setIsLoadingHot(false);
    }
  };

  // Reload when filters change (only via REST if not currently live)
  useEffect(() => {
    if (!isLiveConnected) {
      loadHotActivity();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hotMinScore, hotMinCameraScore, hotOnlyNew, isLiveConnected]);

  // Compact summary for collapsed state
  const hotSummary = useMemo(() => {
    if (!hotData) return null;
    const camCount = hotData.hot_cameras?.length || 0;
    const entCount = hotData.top_recent_entities?.length || 0;
    const newCount = (hotData.top_recent_entities || []).filter((e) => e.is_new).length;
    const parts = [
      `${camCount} camera${camCount === 1 ? '' : 's'}`,
      `${entCount} ${entCount === 1 ? 'entity' : 'entities'}`,
    ];
    if (newCount > 0) parts.push(`${newCount} new`);
    return parts.join(' • ');
  }, [hotData]);

  const toggleHotCard = () => {
    setIsHotExpanded((prev) => !prev);
  };

  // --- Live updates via hot-only WebSocket ---
  const buildCurrentFilters = () => {
    const filters: Record<string, number | boolean> = {};
    if (hotMinScore !== '') filters.min_score = Number(hotMinScore);
    if (hotMinCameraScore !== '') filters.min_camera_score = Number(hotMinCameraScore);
    if (hotOnlyNew) filters.entity_is_new = true;
    return filters;
  };

  const sendFiltersToWs = (ws: WebSocket) => {
    const filters = buildCurrentFilters();
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ command: 'filter', filters }));
    }
  };

  const connectToHotStream = () => {
    if (hotWsRef.current) return; // already connecting/connected

    try {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/api/v1/system/ai-processing-hot-ws`;

      const ws = new WebSocket(wsUrl);
      hotWsRef.current = ws;

      ws.onopen = () => {
        setIsLiveConnected(true);
        // Ask for hot-updates-only mode + current filters
        ws.send(JSON.stringify({ command: 'filter', filters: { ...buildCurrentFilters(), hot_updates_only: true } }));
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'hot_update' && msg.data) {
            setHotData({
              status: 'ok',
              hot_cameras: msg.data.hot_cameras || [],
              top_recent_entities: msg.data.top_recent_entities || [],
              filters_applied: buildCurrentFilters(),
            });
          }
          // ignore pings, stats, etc. for now
        } catch (e) {
          // ignore malformed messages
        }
      };

      ws.onclose = () => {
        setIsLiveConnected(false);
        hotWsRef.current = null;
        // Auto-reconnect if still expanded
        if (isHotExpanded) {
          setTimeout(() => {
            if (isHotExpanded) connectToHotStream();
          }, 2000);
        }
      };

      ws.onerror = () => {
        setIsLiveConnected(false);
      };
    } catch (e) {
      setIsLiveConnected(false);
    }
  };

  const disconnectFromHotStream = () => {
    if (hotWsRef.current) {
      hotWsRef.current.close();
      hotWsRef.current = null;
    }
    setIsLiveConnected(false);
  };

  // Connect when expanded (always for mini), disconnect when collapsed
  useEffect(() => {
    if (effectiveExpanded) {
      // Initial REST load + live connection
      if (!hotData) loadHotActivity();
      connectToHotStream();
    } else {
      disconnectFromHotStream();
    }

    return () => {
      disconnectFromHotStream();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveExpanded]);

  // When filters change while live-connected, push them to the WS
  useEffect(() => {
    if (isLiveConnected && hotWsRef.current) {
      sendFiltersToWs(hotWsRef.current);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hotMinScore, hotMinCameraScore, hotOnlyNew, isLiveConnected]);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <div>
          <CardTitle className="text-base flex items-center gap-2">
            <Flame className="h-5 w-5" />
            {title}
          </CardTitle>
          {effectiveExpanded ? (
            <CardDescription className="text-xs">
              {variant === 'mini'
                ? 'Trending cameras & entities (live)'
                : 'Current hot cameras & entities (exponential decay)'}
            </CardDescription>
          ) : hotSummary ? (
            <div className="text-xs text-muted-foreground mt-0.5 font-mono tabular-nums">
              {hotSummary}
            </div>
          ) : (
            <div className="text-xs text-muted-foreground mt-0.5">Loading…</div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {effectiveExpanded && isLiveConnected && (
            <span className="flex items-center gap-1 text-xs text-emerald-600 font-medium">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              Live
            </span>
          )}
          {effectiveExpanded && (
            <Button
              variant="outline"
              size="sm"
              onClick={loadHotActivity}
              disabled={isLoadingHot}
            >
              <RefreshCw className={`h-4 w-4 mr-1 ${isLoadingHot ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
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

          {variant === 'full' && (
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleHotCard}
              aria-label={isHotExpanded ? 'Collapse hot activity' : 'Expand hot activity'}
            >
              {isHotExpanded ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </Button>
          )}
        </div>
      </CardHeader>

      {effectiveExpanded && (
        <CardContent>
          {/* Filter controls (only in full variant) */}
          {variant === 'full' && (
            <div className="flex flex-wrap items-center gap-4 mb-4 text-sm">
            <div className="flex items-center gap-2">
              <label className="text-muted-foreground">Min entity score</label>
              <input
                type="number"
                step="0.05"
                min="0"
                max="100"
                placeholder="0.0"
                className="w-20 rounded border bg-background px-2 py-1 text-sm"
                value={hotMinScore}
                onChange={(e) =>
                  setHotMinScore(e.target.value === '' ? '' : Number(e.target.value))
                }
              />
            </div>

            <div className="flex items-center gap-2">
              <label className="text-muted-foreground">Min camera score</label>
              <input
                type="number"
                step="0.5"
                min="0"
                max="100"
                placeholder="0.0"
                className="w-20 rounded border bg-background px-2 py-1 text-sm"
                value={hotMinCameraScore}
                onChange={(e) =>
                  setHotMinCameraScore(e.target.value === '' ? '' : Number(e.target.value))
                }
              />
            </div>

            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={hotOnlyNew}
                onChange={(e) => setHotOnlyNew(e.target.checked)}
                className="accent-primary"
              />
              <span>New entities only</span>
            </label>

            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setHotMinScore('');
                setHotMinCameraScore('');
                setHotOnlyNew(false);
              }}
              className="h-7 px-2 text-xs"
            >
              Clear filters
            </Button>

            {hotData?.filters_applied && Object.keys(hotData.filters_applied).length > 0 && (
              <span className="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground">
                {Object.keys(hotData.filters_applied).length} filter
                {Object.keys(hotData.filters_applied).length === 1 ? '' : 's'} active
              </span>
            )}
          </div>
          )}

          {isLoadingHot && !hotData && (
            <div className="text-sm text-muted-foreground">Loading hot lists...</div>
          )}

          {!isLoadingHot && hotData && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Hot Cameras */}
              <div>
                <div className="font-medium text-sm mb-2 flex items-center gap-1">
                  <Camera className="h-4 w-4" /> Hot Cameras
                </div>
                {hotData.hot_cameras?.length ? (
                  <ul className="space-y-1 text-sm">
                    {hotData.hot_cameras.slice(0, displayLimit).map((cam: HotCamera, idx: number) => (
                      <li key={idx} className="flex justify-between border-b pb-1">
                        <span>{cam.name || cam.camera_id}</span>
                        <span className="text-muted-foreground tabular-nums">
                          {cam.score?.toFixed?.(1) ?? cam.score} × {cam.count}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="text-xs text-muted-foreground">
                    No cameras match current filters
                  </div>
                )}
              </div>

              {/* Top Recent Entities */}
              <div>
                <div className="font-medium text-sm mb-2 flex items-center gap-1">
                  <Activity className="h-4 w-4" /> Top Recent Entities
                </div>
                {hotData.top_recent_entities?.length ? (
                  <ul className="space-y-1 text-sm">
                    {hotData.top_recent_entities.slice(0, displayLimit).map((ent: HotEntity, idx: number) => (
                      <li key={idx} className="flex justify-between border-b pb-1">
                        <span>
                          {ent.name || ent.entity_id}
                          {ent.is_new && (
                            <span className="ml-1 text-[10px] px-1 py-0.5 bg-blue-100 text-blue-700 rounded">
                              NEW
                            </span>
                          )}
                        </span>
                        <span className="text-muted-foreground tabular-nums">
                          {ent.score?.toFixed?.(2) ?? ent.score}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="text-xs text-muted-foreground">
                    No entities match current filters
                  </div>
                )}
              </div>
            </div>
          )}

          {!hotData && !isLoadingHot && (
            <div className="text-xs text-muted-foreground">
              Hot lists will appear here when the coordinator has processed events.
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}
