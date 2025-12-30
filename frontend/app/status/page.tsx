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
} from 'lucide-react';

import { apiClient } from '@/lib/api-client';
import type { SystemHealth, LogEntry, LogsResponse } from '@/types/monitoring';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

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
      status: 'online', // Would need separate endpoint to check
      icon: <Brain className="h-5 w-5" />,
      description: 'Vision API providers',
    },
  ];

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
                      {new Date(log.timestamp).toLocaleTimeString()}
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
