/**
 * System Settings Types
 * Types for system configuration and settings management
 */

export type AIModel = 'gpt-4o-mini' | 'claude-3-haiku' | 'gemini-flash';
export type DetectionMethod = 'background_subtraction' | 'frame_difference';
export type TimeFormat = '12h' | '24h';
export type DateFormat = 'MM/DD/YYYY' | 'DD/MM/YYYY' | 'YYYY-MM-DD';
export type ThumbnailStorage = 'filesystem' | 'database';

// Story P8-2.5: Frame Sampling Strategy Selection
export type FrameSamplingStrategy = 'uniform' | 'adaptive' | 'hybrid';

export interface SystemSettings {
  // General
  system_name: string;
  timezone: string;
  language: string;
  date_format: DateFormat;
  time_format: TimeFormat;

  // AI Models
  primary_model: AIModel;
  primary_api_key: string; // Encrypted in backend
  fallback_model: AIModel | null;
  description_prompt: string;

  // Story P9-3.5: Summary Prompt Customization
  summary_prompt?: string;  // Custom prompt for activity summaries

  // Motion Detection
  motion_sensitivity: number; // 0-100
  detection_method: DetectionMethod;
  cooldown_period: number; // seconds
  min_motion_area: number; // 1-10 percent
  save_debug_images: boolean;

  // Data & Privacy
  retention_days: number; // -1 for forever
  thumbnail_storage: ThumbnailStorage;
  auto_cleanup: boolean;

  // Story P4-7.3: Anomaly Detection Settings
  anomaly_enabled?: boolean;  // Enable anomaly scoring (default: true)
  anomaly_low_threshold?: number;  // Low/medium threshold (default: 0.3)
  anomaly_high_threshold?: number;  // Medium/high threshold (default: 0.6)

  // Story P3-7.3: Cost Cap Settings
  ai_daily_cost_cap?: number | null;  // Daily AI cost cap in dollars
  ai_monthly_cost_cap?: number | null;  // Monthly AI cost cap in dollars

  // Story P8-2.3: Configurable Frame Count Setting
  analysis_frame_count?: 5 | 10 | 15 | 20;  // Number of frames for AI analysis (default: 10)

  // Story P8-2.5: Frame Sampling Strategy Selection
  frame_sampling_strategy?: FrameSamplingStrategy;  // Frame selection strategy (default: uniform)

  // Story P8-3.2: Full Motion Video Storage
  store_motion_videos?: boolean;  // Download and store full motion videos (default: false)
  video_retention_days?: number;  // Days to retain videos (default: 30)

  // Story P9-3.2: OCR Frame Overlay Extraction
  attempt_ocr_extraction?: boolean;  // Attempt OCR on frame overlays (default: false)
}

export interface StorageStats {
  total_events: number;
  database_mb: number;
  thumbnails_mb: number;
  total_mb: number;
}

export type AIProvider = 'openai' | 'anthropic' | 'google' | 'grok';

export interface AIKeyTestRequest {
  provider: AIProvider;
  api_key: string;
}

export interface AIKeyTestResponse {
  valid: boolean;
  message: string;
  provider: string;
}

export interface DeleteDataRequest {
  confirmation: boolean;
}

export interface DeleteDataResponse {
  deleted_count: number;
  success: boolean;
}

/**
 * AI Provider Configuration for multi-provider management
 */
export interface AIProviderConfig {
  id: AIProvider;
  name: string;
  description: string;
  isConfigured: boolean;
  model?: string;
}

/**
 * AI Provider order for fallback chain configuration
 */
export type AIProviderOrder = AIProvider[];

/**
 * AI Usage Types for Cost Monitoring Dashboard
 * Story P3-7.2: Build Cost Dashboard UI
 */

export interface IAIUsagePeriod {
  start: string;
  end: string;
}

export interface IAIUsageByDate {
  date: string;
  cost: number;
  requests: number;
}

export interface IAIUsageByCamera {
  camera_id: string;
  camera_name: string;
  cost: number;
  requests: number;
}

export interface IAIUsageByProvider {
  provider: string;
  cost: number;
  requests: number;
}

export interface IAIUsageByMode {
  mode: string;
  cost: number;
  requests: number;
}

export interface IAIUsageResponse {
  total_cost: number;
  total_requests: number;
  period: IAIUsagePeriod;
  by_date: IAIUsageByDate[];
  by_camera: IAIUsageByCamera[];
  by_provider: IAIUsageByProvider[];
  by_mode: IAIUsageByMode[];
}

export interface IAIUsageQueryParams {
  start_date?: string;
  end_date?: string;
  days?: number;
  provider?: string;
  camera_id?: number;
}

/**
 * Cost Cap Status for enforcement and UI display
 * Story P3-7.3: Implement Daily/Monthly Cost Caps
 */
export interface ICostCapStatus {
  daily_cost: number;
  daily_cap: number | null;  // null = no limit
  daily_percent: number;     // 0-100, 0 if no cap
  monthly_cost: number;
  monthly_cap: number | null;
  monthly_percent: number;
  is_paused: boolean;
  pause_reason: 'cost_cap_daily' | 'cost_cap_monthly' | null;
}

/**
 * MQTT Configuration Types for Home Assistant Integration
 * Story P4-2.4: Integration Settings UI
 */

export interface MQTTConfigResponse {
  id: string;
  broker_host: string;
  broker_port: number;
  username: string | null;
  topic_prefix: string;
  discovery_prefix: string;
  discovery_enabled: boolean;
  qos: 0 | 1 | 2;
  enabled: boolean;
  retain_messages: boolean;
  use_tls: boolean;
  message_expiry_seconds: number;
  availability_topic: string;  // Story P5-6.2
  birth_message: string;       // Story P5-6.2
  will_message: string;        // Story P5-6.2
  has_password: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface MQTTConfigUpdate {
  broker_host: string;
  broker_port: number;
  username?: string;
  password?: string;
  topic_prefix: string;
  discovery_prefix: string;
  discovery_enabled: boolean;
  qos: 0 | 1 | 2;
  enabled: boolean;
  retain_messages: boolean;
  use_tls: boolean;
  message_expiry_seconds: number;
  availability_topic: string;  // Story P5-6.2
  birth_message: string;       // Story P5-6.2
  will_message: string;        // Story P5-6.2
}

export interface MQTTStatusResponse {
  connected: boolean;
  broker: string | null;
  last_connected_at: string | null;
  messages_published: number;
  last_error: string | null;
  reconnect_attempt: number;
}

export interface MQTTTestRequest {
  broker_host: string;
  broker_port: number;
  username?: string;
  password?: string;
  use_tls: boolean;
}

export interface MQTTTestResponse {
  success: boolean;
  message: string;
}

export interface MQTTPublishDiscoveryResponse {
  success: boolean;
  message: string;
  cameras_published: number;
}
