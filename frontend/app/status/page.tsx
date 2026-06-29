/**
 * System Status Page (Story 6.2, AC: #7)
 * Displays system health, service status, and recent logs
 */

'use client';

import { useState, useEffect } from 'react';
import {
  Activity,
  Camera,
  Database,
  Brain,
  Server,
  RefreshCw,
  Download,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  Cpu,
  HardDrive,
  MemoryStick,
  RotateCcw,
  Shield,
} from 'lucide-react';
import { parseApiDate, formatRelative } from '@/lib/datetime';

import { apiClient } from '@/lib/api-client';
import type { SystemHealth, LogEntry, LogsResponse } from '@/types/monitoring';
import { useAuth } from '@/contexts/AuthContext';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { HotActivityCard } from '@/components/dashboard/HotActivityCard';
import { AICostTrendsCard } from '@/components/dashboard/AICostTrendsCard';

interface ServiceStatus {
  name: string;
  status: 'online' | 'offline' | 'unknown';
  icon: React.ReactNode;
  description: string;
}

export default function StatusPage() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [logLevel, setLogLevel] = useState<string>('all');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // AI Resilience reset tracking
  const [lastCircuitBreakerReset, setLastCircuitBreakerReset] = useState<string | null>(null);

  const auth = useAuth();
  const isAdmin = auth.isAdmin;

  // Load data on mount and set up refresh interval
  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000); // Refresh every 30s
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reload logs when level filter changes
  useEffect(() => {
    loadLogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [logLevel]);

  const loadData = async () => {
    setIsRefreshing(true);
    try {
      await Promise.all([loadHealth(), loadLogs()]);

      // Also refresh AI Resilience data
      try {
        const res = await apiClient.getAIResilience();
        setAiResilience(res);
      } catch (e) {
        // Non-critical
      }

      // Hot Activity refreshes itself via the self-contained <HotActivityCard />.

      setLastUpdated(new Date());
    } catch (error) {
      console.error('Failed to load status data:', error);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  const loadHealth = async () => {
    try {
      const data = await apiClient.monitoring.health();
      setHealth(data);
    } catch (error) {
      console.error('Failed to load health:', error);
      setHealth({ status: 'unhealthy', camera_count: 0 });
    }
  };

  const loadLogs = async () => {
    try {
      const params = {
        limit: 50,
        ...(logLevel !== 'all' && { level: logLevel }),
      };
      const data: LogsResponse = await apiClient.monitoring.logs(params);
      setLogs(data.entries);
    } catch (error) {
      console.error('Failed to load logs:', error);
      setLogs([]);
    }
  };

  const handleDownloadLogs = async () => {
    // TODO: Implement log download API endpoint (tracked in backlog)
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
      case 'online':
        return <CheckCircle2 className="h-5 w-5 text-green-500" />;
      case 'degraded':
        return <AlertTriangle className="h-5 w-5 text-yellow-500" />;
      default:
        return <XCircle className="h-5 w-5 text-red-500" />;
    }
  };

  const getLogLevelColor = (level: string) => {
    switch (level.toUpperCase()) {
      case 'DEBUG':
        return 'text-gray-500';
      case 'INFO':
        return 'text-blue-500';
      case 'WARNING':
        return 'text-yellow-500';
      case 'ERROR':
        return 'text-red-500';
      case 'CRITICAL':
        return 'text-red-700 font-bold';
      default:
        return 'text-gray-500';
    }
  };

  const services: ServiceStatus[] = [
    {
      name: 'API Server',
      status: health ? 'online' : 'unknown',
      icon: <Server className="h-5 w-5" />,
      description: 'FastAPI backend service',
    },
    {
      name: 'Database',
      status: health ? 'online' : 'unknown',
      icon: <Database className="h-5 w-5" />,
      description: 'SQLite database connection',
    },
    {
      name: 'Cameras',
      status: health && health.camera_count > 0 ? 'online' : 'offline',
      icon: <Camera className="h-5 w-5" />,
      description: `${health?.camera_count || 0} camera(s) connected`,
    },
    {
      name: 'AI Service',
      status: 'online',
      icon: <Brain className="h-5 w-5" />,
      description: 'Vision API providers',
    },
  ];

  // AI Resilience (Circuit Breaker) Status
  const [aiResilience, setAiResilience] = useState<any>(null);

  useEffect(() => {
    const loadResilience = async () => {
      try {
        const res = await apiClient.getAIResilience();
        setAiResilience(res);

        // Prefer backend last_reset if available (visible to all admins)
        if (res?.last_reset) {
          setLastCircuitBreakerReset(res.last_reset);
        } else {
          // Fallback to localStorage (for the user who performed the reset)
          const stored = localStorage.getItem('lastCircuitBreakerReset');
          if (stored) setLastCircuitBreakerReset(stored);
        }
      } catch (e) {
        // Silently fail - not critical for status page
      }
    };
    loadResilience();
  }, []);

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-7xl space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">System Status</h1>
          <p className="text-muted-foreground">
            Monitor system health and view logs
          </p>
        </div>
        <div className="flex items-center gap-4">
          {lastUpdated && (
            <span className="flex items-center gap-2 text-sm text-muted-foreground">
              <Clock className="h-4 w-4" />
              Last updated: {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <Button
            variant="outline"
            onClick={loadData}
            disabled={isRefreshing}
          >
            <RefreshCw className={`mr-2 h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Overall Status Banner */}
      <Card className={`border-2 ${
        health?.status === 'healthy' ? 'border-green-500 bg-green-50 dark:bg-green-950/20' :
        health?.status === 'degraded' ? 'border-yellow-500 bg-yellow-50 dark:bg-yellow-950/20' :
        'border-red-500 bg-red-50 dark:bg-red-950/20'
      }`}>
        <CardContent className="flex items-center gap-4 p-6">
          <Activity className={`h-10 w-10 ${
            health?.status === 'healthy' ? 'text-green-500' :
            health?.status === 'degraded' ? 'text-yellow-500' :
            'text-red-500'
          }`} />
          <div>
            <h2 className="text-2xl font-semibold capitalize">
              System {health?.status || 'Unknown'}
            </h2>
            <p className="text-muted-foreground">
              All services operational
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Service Status Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {services.map((service) => (
          <Card key={service.name}>
            <CardContent className="flex items-center gap-4 p-4">
              <div className="rounded-full bg-muted p-2">
                {service.icon}
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{service.name}</span>
                  {getStatusIcon(service.status)}
                </div>
                <p className="text-sm text-muted-foreground">
                  {service.description}
                </p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* AI Resilience Status (Phase A) */}
      {aiResilience && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <Brain className="h-5 w-5" />
                AI Provider Circuit Breakers
              </CardTitle>
              <CardDescription className="text-xs flex items-center gap-2">
                Real-time protection status for vision providers
                {lastCircuitBreakerReset && (
                  <span className="text-[10px] text-muted-foreground">
                    · Last reset {formatRelative(lastCircuitBreakerReset)}
                  </span>
                )}
              </CardDescription>
            </div>

            {isAdmin && (
              <Button
                variant="outline"
                size="sm"
                onClick={async () => {
                  if (!confirm("Reset ALL AI circuit breakers to CLOSED state?")) return;

                  try {
                    await apiClient.resetAICircuitBreaker("default");
                    toast.success("All circuit breakers have been reset to CLOSED");
                    // Refresh the data (backend now stores last_reset globally)
                    const res = await apiClient.getAIResilience();
                    setAiResilience(res);
                    if (res?.last_reset) {
                      setLastCircuitBreakerReset(res.last_reset);
                    }
                  } catch (e) {
                    toast.error("Failed to reset all breakers");
                  }
                }}
                className="h-8 px-3 text-xs"
              >
                <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
                Reset All
              </Button>
            )}
          </CardHeader>

          <CardContent>
            <div className="flex flex-wrap gap-3">
              {Object.entries(aiResilience).map(([name, status]: [string, any]) => {
                if (!status) return null;
                const color = status.state === 'closed' ? 'bg-green-500' : 
                             status.state === 'open' ? 'bg-red-500' : 'bg-yellow-500';
                return (
                  <div key={name} className="flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm">
                    <span className="font-medium capitalize">{name}</span>
                    <div className={`h-2 w-2 rounded-full ${color}`} />
                    <span className="text-xs text-muted-foreground capitalize">{status.state}</span>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Hot Activity - powered by AIProcessingCoordinator hot lists */}
      <HotActivityCard />

      {/* AI Cost & Token Trends - Full view */}
      <AICostTrendsCard variant="full" />

      {/* Protect WebSocket Health (Story #437) */}
      {health?.protect_ws && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Shield className="h-5 w-5" />
              UniFi Protect WebSocket
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <div className="text-muted-foreground text-xs">Status</div>
                <div className={`font-medium flex items-center gap-2 ${
                  health.protect_ws.is_healthy ? 'text-green-600' : 'text-red-600'
                }`}>
                  {health.protect_ws.state}
                  {health.protect_ws.is_healthy ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : (
                    <XCircle className="h-4 w-4" />
                  )}
                </div>
              </div>
              <div>
                <div className="text-muted-foreground text-xs">Last Message</div>
                <div className="font-medium">
                  {health.protect_ws.last_message_age_seconds !== null
                    ? `${health.protect_ws.last_message_age_seconds}s ago`
                    : 'Never'}
                </div>
              </div>
              <div>
                <div className="text-muted-foreground text-xs">Reconnect Attempts</div>
                <div className="font-medium">{health.protect_ws.reconnect_attempts}</div>
              </div>
              <div>
                <div className="text-muted-foreground text-xs">Controller</div>
                <div className="font-medium truncate">
                  {health.protect_ws.controller_name || '—'}
                </div>
              </div>
            </div>
            {health.protect_ws.last_error && (
              <div className="mt-3 text-xs text-red-600">
                Last error: {health.protect_ws.last_error}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* System Resources */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Cpu className="h-4 w-4" />
              CPU Usage
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">--</div>
            <p className="text-sm text-muted-foreground">
              Requires metrics endpoint polling
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <MemoryStick className="h-4 w-4" />
              Memory Usage
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">--</div>
            <p className="text-sm text-muted-foreground">
              Requires metrics endpoint polling
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <HardDrive className="h-4 w-4" />
              Disk Usage
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">--</div>
            <p className="text-sm text-muted-foreground">
              Requires metrics endpoint polling
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Recent Logs */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Recent Logs</CardTitle>
              <CardDescription>
                Latest application log entries
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Select value={logLevel} onValueChange={setLogLevel}>
                <SelectTrigger className="w-32">
                  <SelectValue placeholder="Log Level" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Levels</SelectItem>
                  <SelectItem value="DEBUG">Debug</SelectItem>
                  <SelectItem value="INFO">Info</SelectItem>
                  <SelectItem value="WARNING">Warning</SelectItem>
                  <SelectItem value="ERROR">Error</SelectItem>
                  <SelectItem value="CRITICAL">Critical</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="outline" onClick={handleDownloadLogs}>
                <Download className="mr-2 h-4 w-4" />
                Download
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="max-h-96 overflow-y-auto rounded-lg border bg-muted/50 p-4 font-mono text-sm">
            {logs.length === 0 ? (
              <p className="text-center text-muted-foreground">
                No log entries found
              </p>
            ) : (
              <div className="space-y-1">
                {logs.map((log, index) => (
                  <div key={index} className="flex gap-2 border-b border-muted pb-1 last:border-0">
                    <span className="shrink-0 text-muted-foreground">
                      {parseApiDate(log.timestamp)!.toLocaleTimeString()}
                    </span>
                    <span className={`shrink-0 w-16 ${getLogLevelColor(log.level)}`}>
                      [{log.level}]
                    </span>
                    <span className="shrink-0 text-muted-foreground">
                      {log.module || log.logger || '-'}
                    </span>
                    <span className="flex-1 break-all">
                      {log.message}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
