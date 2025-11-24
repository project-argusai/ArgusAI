/**
 * System Settings Types
 * Types for system configuration and settings management
 */

export type AIModel = 'gpt-4o-mini' | 'claude-3-haiku' | 'gemini-flash';
export type DetectionMethod = 'background_subtraction' | 'frame_difference';
export type TimeFormat = '12h' | '24h';
export type DateFormat = 'MM/DD/YYYY' | 'DD/MM/YYYY' | 'YYYY-MM-DD';
export type ThumbnailStorage = 'filesystem' | 'database';

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
}

export interface StorageStats {
  total_events: number;
  database_mb: number;
  thumbnails_mb: number;
  total_mb: number;
}

export type AIProvider = 'openai' | 'anthropic' | 'google';

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
