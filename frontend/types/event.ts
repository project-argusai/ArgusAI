/**
 * Event-related TypeScript interfaces for Live Object AI Classifier
 */

/**
 * Main Event interface matching backend Event model
 */
/**
 * Event source types - matches backend Event.source_type
 */
export type SourceType = 'rtsp' | 'usb' | 'protect';

/**
 * Smart detection types from UniFi Protect
 */
export type SmartDetectionType = 'person' | 'vehicle' | 'package' | 'animal' | 'motion' | 'ring';

/**
 * Story P3-3.4: Analysis mode types for AI event processing
 * Matches backend Event.analysis_mode field
 */
export type AnalysisMode = 'single_frame' | 'multi_frame' | 'video_native';

/**
 * Story P2-4.4: Correlated event info for multi-camera event display
 */
export interface ICorrelatedEvent {
  id: string;                     // Event UUID
  camera_name: string;            // Camera name (not ID) for display
  thumbnail_url: string | null;   // Full URL to thumbnail image
  timestamp: string;              // ISO 8601 datetime
}

export interface IEvent {
  id: string;                     // UUID
  camera_id: string;              // UUID foreign key
  camera_name?: string;           // Human-readable camera name for display (FF-003)
  timestamp: string;              // ISO 8601 datetime
  description: string;            // AI-generated description
  confidence: number;             // 0-100
  objects_detected: string[];     // ["person", "vehicle", "animal", "package", "unknown"]
  thumbnail_path: string | null;
  thumbnail_base64: string | null;
  alert_triggered: boolean;
  created_at: string;             // ISO 8601 datetime
  // Phase 2: UniFi Protect event source fields
  source_type: SourceType;        // Event source: 'rtsp', 'usb', 'protect'
  smart_detection_type: SmartDetectionType | null; // Protect smart detection type
  // Story P2-4.1: Doorbell ring event support
  is_doorbell_ring: boolean;      // True if event was triggered by doorbell ring
  // Story P2-4.4: Multi-camera event correlation
  correlation_group_id?: string | null;  // UUID linking correlated events across cameras
  correlated_events?: ICorrelatedEvent[]; // Related events from same correlation group
  // Story P2-5.3: AI provider tracking
  provider_used?: string | null;  // AI provider: openai, grok, claude, gemini
  // Story P3-3.4: Analysis mode tracking
  analysis_mode?: AnalysisMode | null;  // Analysis mode used: single_frame, multi_frame, video_native
  frame_count_used?: number | null;     // Number of frames sent to AI (for multi_frame mode)
  fallback_reason?: string | null;      // Reason for fallback to lower mode (e.g., "clip_download_failed")
  // Story P3-6.1: AI confidence scoring
  ai_confidence?: number | null;        // AI self-reported confidence 0-100
  // Story P3-6.2: Vague description detection
  low_confidence?: boolean;             // True if ai_confidence < 50 OR description is vague
  vague_reason?: string | null;         // Human-readable reason why flagged as vague
  // Story P3-6.4: Re-analysis tracking
  reanalyzed_at?: string | null;        // Timestamp of last re-analysis (null = never re-analyzed)
  reanalysis_count?: number;            // Number of re-analyses performed
  // Story P3-7.1: AI cost tracking
  ai_cost?: number | null;              // Estimated cost in USD for AI analysis
  // Story P3-7.5: Key frames for gallery display
  key_frames_base64?: string[] | null;  // Base64-encoded key frames used for AI analysis
  frame_timestamps?: number[] | null;   // Timestamps in seconds for each key frame
}

/**
 * Event filters for querying events API
 */
export interface IEventFilters {
  search?: string;                // Full-text search on description
  camera_id?: string;             // Filter by camera UUID
  start_date?: string;            // ISO 8601 datetime
  end_date?: string;              // ISO 8601 datetime
  objects?: string[];             // Filter by detected objects
  min_confidence?: number;        // Minimum confidence score (0-100)
  source_type?: SourceType;       // Filter by event source (Phase 2)
  smart_detection_type?: SmartDetectionType; // Filter by smart detection type (Phase 2)
  // Story P3-7.6: Analysis mode filtering
  analysis_mode?: AnalysisMode;   // Filter by analysis mode
  has_fallback?: boolean;         // Filter events with fallback_reason (True = has fallback)
  low_confidence?: boolean;       // Filter by low confidence flag (True = uncertain descriptions)
}

/**
 * Paginated events response from API
 * Matches backend EventListResponse schema
 */
export interface IEventsResponse {
  events: IEvent[];
  total_count: number;
  has_more: boolean;
  next_offset: number | null;
  limit: number;
  offset: number;
}

/**
 * Object detection types
 */
export type DetectedObject = 'person' | 'vehicle' | 'animal' | 'package' | 'unknown';

/**
 * Helper to get confidence level classification
 * Story P3-6.3: Updated thresholds per AC1:
 * - High: 80-100
 * - Medium: 50-79
 * - Low: 0-49
 */
export function getConfidenceLevel(confidence: number): 'high' | 'medium' | 'low' {
  if (confidence >= 80) return 'high';
  if (confidence >= 50) return 'medium';
  return 'low';
}

/**
 * Helper to get confidence color class
 * Story P3-6.3: Updated thresholds per AC1
 */
export function getConfidenceColor(confidence: number): string {
  if (confidence >= 80) return 'text-green-600 bg-green-50';
  if (confidence >= 50) return 'text-yellow-600 bg-yellow-50';
  return 'text-red-600 bg-red-50';
}

/**
 * Story P3-6.3: AI confidence level type
 */
export type AIConfidenceLevel = 'high' | 'medium' | 'low';

/**
 * Story P3-6.3: Get AI confidence level from ai_confidence score
 * Uses same thresholds as getConfidenceLevel for consistency
 */
export function getAIConfidenceLevel(aiConfidence: number | null | undefined): AIConfidenceLevel | null {
  if (aiConfidence == null) return null;
  if (aiConfidence >= 80) return 'high';
  if (aiConfidence >= 50) return 'medium';
  return 'low';
}
