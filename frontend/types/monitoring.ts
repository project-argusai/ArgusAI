/**
 * Monitoring Types (Story 6.2)
 * Type definitions for system health monitoring and logging
 */

export interface SystemHealth {
  status: 'healthy' | 'degraded' | 'unhealthy';
  camera_count: number;
  uptime_seconds?: number;
  version?: string;
  // UniFi Protect WebSocket health (Story #437) — present only when a
  // Protect controller is configured; the status page guards on its presence.
  protect_ws?: {
    is_healthy: boolean;
    state: string;
    last_message_age_seconds: number | null;
    reconnect_attempts: number;
    controller_name?: string | null;
    last_error?: string | null;
  };
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
  source?: string;
  search?: string;
  start_date?: string;
  end_date?: string;
  start_time?: string;
  end_time?: string;
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

/**
 * A single recognized-entity reference attached to an AI processing record
 * (either the early/fast pass or the final pass).
 */
export interface AIProcessingEntityRef {
  entity_id?: string;
  entity_name?: string | null;
  is_new?: boolean;
}

/**
 * One entry from the AI processing coordinator ring buffer
 * (`/system/ai-processing-recent` → `recent_activity[]`, also streamed via SSE).
 */
export interface AIProcessingRecord {
  timestamp: number;
  camera_id?: string;
  provider?: string | null;
  description?: string | null;
  success?: boolean;
  analysis_skipped?: boolean;
  analysis_skipped_reason?: string | null;
  low_confidence?: boolean;
  ocr_used?: boolean;
  regenerated?: boolean;
  ai_cost?: number | null;
  ai_response_time_ms?: number | null;
  error?: string | null;
  entity_early?: AIProcessingEntityRef | null;
  entity_final?: AIProcessingEntityRef | null;
}

/** A trending camera surfaced by the coordinator hot lists. */
export interface HotCamera {
  camera_id?: string;
  name?: string | null;
  score?: number;
  count?: number;
}

/** A trending recognized entity surfaced by the coordinator hot lists. */
export interface HotEntity {
  entity_id?: string;
  name?: string | null;
  score?: number;
  is_new?: boolean;
  target?: string;
}

/**
 * Response shape for `/system/ai-processing-hot` and the matching hot-update
 * WebSocket/SSE payloads.
 */
export interface HotActivityData {
  status?: string;
  hot_cameras: HotCamera[];
  top_recent_entities: HotEntity[];
  filters_applied?: Record<string, unknown>;
}

/** One bucketed point from `/system/ai-cost-trends` → `trends[]`. */
export interface AICostTrendPoint {
  bucket: string;
  calls: number;
  total_cost: number;
  total_tokens: number;
  avg_response_time_ms: number | null;
}

/** Circuit-breaker tuning knobs for a single AI provider. */
export interface CircuitBreakerConfig {
  failure_threshold: number;
  recovery_timeout: number;
  half_open_max_calls: number;
  failure_rate_threshold: number;
  minimum_calls_in_window: number;
  window_duration_seconds: number;
}

/** Live circuit-breaker status for a single AI provider. */
export interface CircuitBreakerStatus {
  provider: string;
  config: CircuitBreakerConfig;
  state: 'closed' | 'open' | 'half_open';
  failure_count: number;
  current_failure_rate: number | null;
  recent_window_size: number;
  last_failure_time: string | null;
  recent_transitions?: Array<{
    timestamp: number;
    from_state?: string;
    to_state?: string;
    reason?: string;
  }>;
}

/**
 * Response shape for `/system/ai-resilience` — per-provider circuit-breaker
 * status keyed by provider name, plus an optional global last-reset marker.
 */
export interface AIResilienceData {
  default: CircuitBreakerStatus;
  openai?: CircuitBreakerStatus;
  grok?: CircuitBreakerStatus;
  claude?: CircuitBreakerStatus;
  gemini?: CircuitBreakerStatus;
  last_reset?: string | null;
}
