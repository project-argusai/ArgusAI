/**
 * Monitoring Types (Story 6.2)
 * Type definitions for system health monitoring and logging
 */

export interface SystemHealth {
  status: 'healthy' | 'degraded' | 'unhealthy';
  camera_count: number;
  uptime_seconds?: number;
  version?: string;
}

export interface ServiceStatus {
  name: string;
  status: 'online' | 'offline' | 'degraded';
  latency_ms?: number;
  last_check?: string;
  error?: string;
}

export interface SystemMetrics {
  cpu_percent: number;
  memory_percent: number;
  memory_used_mb: number;
  disk_percent: number;
  disk_used_gb: number;
}

export interface EventMetrics {
  events_today: number;
  events_processed: number;
  processing_errors: number;
  error_rate_percent: number;
  avg_processing_time_ms: number;
}

export interface AIMetrics {
  calls_today: number;
  total_calls: number;
  success_rate_percent: number;
  total_cost_usd: number;
  avg_response_time_ms: number;
  provider_breakdown: {
    [provider: string]: {
      calls: number;
      success_rate: number;
      cost: number;
    };
  };
}

export interface LogEntry {
  timestamp: string;
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
  message: string;
  module?: string;
  logger?: string;
  request_id?: string;
  function?: string;
  line?: number;
  extra?: Record<string, unknown>;
}

export interface LogsResponse {
  entries: LogEntry[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface LogsQueryParams {
  level?: string;
  module?: string;
  search?: string;
  start_date?: string;
  end_date?: string;
  limit?: number;
  offset?: number;
}

export interface LogFilesResponse {
  files: string[];
  directory: string;
}

export interface StatusPageData {
  health: SystemHealth;
  services: ServiceStatus[];
  system: SystemMetrics;
  events: EventMetrics;
  ai: AIMetrics;
}
