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
 */
export function getConfidenceLevel(confidence: number): 'high' | 'medium' | 'low' {
  if (confidence >= 90) return 'high';
  if (confidence >= 70) return 'medium';
  return 'low';
}

/**
 * Helper to get confidence color class
 */
export function getConfidenceColor(confidence: number): string {
  if (confidence >= 90) return 'text-green-600 bg-green-50';
  if (confidence >= 70) return 'text-yellow-600 bg-yellow-50';
  return 'text-red-600 bg-red-50';
}
