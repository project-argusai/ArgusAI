/**
 * Event-related TypeScript interfaces for ArgusAI
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

/**
 * Story P4-5.1: Event Feedback interface for user ratings and corrections
 * Story P9-3.3: Added correction_type for specific feedback types
 */
export interface IEventFeedback {
  id: string;                     // Feedback UUID
  event_id: string;               // Event UUID
  camera_id?: string | null;      // Story P4-5.2: Denormalized camera ID for aggregate stats
  rating: 'helpful' | 'not_helpful';  // User rating
  correction: string | null;      // Optional correction text
  correction_type?: 'not_package' | null;  // Story P9-3.3: Correction type
  created_at: string;             // ISO 8601 datetime
  updated_at?: string | null;     // ISO 8601 datetime
}

/**
 * Story P4-5.2: Per-camera feedback statistics
 */
export interface ICameraFeedbackStats {
  camera_id: string;
  camera_name: string;
  helpful_count: number;
  not_helpful_count: number;
  accuracy_rate: number;          // Percentage 0-100
}

/**
 * Story P4-5.2: Daily feedback statistics for trend analysis
 */
export interface IDailyFeedbackStats {
  date: string;                   // YYYY-MM-DD format
  helpful_count: number;
  not_helpful_count: number;
}

/**
 * Story P4-5.2: Correction summary for common patterns
 */
export interface ICorrectionSummary {
  correction_text: string;
  count: number;
}

/**
 * Story P4-5.2: Aggregate feedback statistics response
 */
export interface IFeedbackStats {
  total_count: number;
  helpful_count: number;
  not_helpful_count: number;
  accuracy_rate: number;                         // Percentage 0-100
  feedback_by_camera: Record<string, ICameraFeedbackStats>;
  daily_trend: IDailyFeedbackStats[];
  top_corrections: ICorrectionSummary[];
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
  // Story P4-5.1: User feedback
  feedback?: IEventFeedback | null;     // User feedback on this event's description
  // Story P4-7.2: Anomaly scoring
  anomaly_score?: number | null;        // Anomaly score 0.0-1.0 (null = not scored)
  // Story P8-3.2: Full motion video storage
  video_path?: string | null;           // Path to stored video file (null = no video stored)
}

/**
 * Event filters for querying events API
 */
export interface IEventFilters {
  // Pagination
  skip?: number;                  // Number of records to skip
  limit?: number;                 // Max records to return
  // Text search
  search?: string;                // Full-text search on description
  // Camera filtering
  camera_id?: string;             // Filter by camera UUID
  // Time filtering
  start_date?: string;            // ISO 8601 datetime (alias for start_time)
  end_date?: string;              // ISO 8601 datetime (alias for end_time)
  start_time?: string;            // ISO 8601 datetime
  end_time?: string;              // ISO 8601 datetime
  time_range?: string;            // Predefined time range (e.g., '1h', '24h', '7d')
  // Object filtering
  objects?: string[];             // Filter by detected objects
  min_confidence?: number;        // Minimum confidence score (0-100)
  // Source filtering
  source_type?: SourceType;       // Filter by event source (Phase 2)
  smart_detection_type?: SmartDetectionType; // Filter by smart detection type (Phase 2)
  // Story P3-7.6: Analysis mode filtering
  analysis_mode?: AnalysisMode;   // Filter by analysis mode
  has_fallback?: boolean;         // Filter events with fallback_reason (True = has fallback)
  low_confidence?: boolean;       // Filter by low confidence flag (True = uncertain descriptions)
  has_thumbnail?: boolean;        // Filter by thumbnail presence
  // Story P4-7.3: Anomaly filtering
  anomaly_severity?: 'low' | 'medium' | 'high';  // Filter by anomaly severity
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

// ==============================================================================
// Story P4-5.4: Prompt Insights Types
// ==============================================================================

/**
 * Correction categories identified by feedback analysis
 */
export type CorrectionCategory =
  | 'object_misidentification'
  | 'action_wrong'
  | 'missing_detail'
  | 'context_error'
  | 'general';

/**
 * A suggestion for improving the AI description prompt
 */
export interface IPromptSuggestion {
  id: string;
  category: CorrectionCategory;
  suggestion_text: string;
  example_corrections: string[];
  confidence: number;     // 0.0 to 1.0
  impact_score: number;   // 0.0 to 1.0
  camera_id?: string | null;
}

/**
 * Per-camera analysis insights
 */
export interface ICameraInsight {
  camera_id: string;
  camera_name: string;
  accuracy_rate: number;  // 0 to 100
  sample_count: number;
  top_categories: CorrectionCategory[];
  suggestions: IPromptSuggestion[];
}

/**
 * Response from GET /api/v1/feedback/prompt-insights
 */
export interface IPromptInsightsResponse {
  suggestions: IPromptSuggestion[];
  camera_insights: Record<string, ICameraInsight>;
  sample_count: number;
  confidence: number;     // 0.0 to 1.0
  min_samples_met: boolean;
}

/**
 * Request body for POST /api/v1/feedback/prompt-insights/apply
 */
export interface IApplySuggestionRequest {
  suggestion_id: string;
  camera_id?: string | null;
}

/**
 * Response from POST /api/v1/feedback/prompt-insights/apply
 */
export interface IApplySuggestionResponse {
  success: boolean;
  new_prompt: string;
  prompt_version: number;
  message: string;
}

/**
 * A/B test accuracy statistics for one variant
 */
export interface IABTestAccuracyStats {
  variant: 'control' | 'experiment';
  event_count: number;
  helpful_count: number;
  not_helpful_count: number;
  accuracy_rate: number;  // 0 to 100
}

/**
 * Response from GET /api/v1/feedback/ab-test/results
 */
export interface IABTestResultsResponse {
  control: IABTestAccuracyStats;
  experiment: IABTestAccuracyStats;
  winner: 'control' | 'experiment' | null;
  confidence: number;     // 0.0 to 1.0
  is_significant: boolean;
  message: string;
}

/**
 * A prompt history entry
 */
export interface IPromptHistoryEntry {
  id: string;
  prompt_version: number;
  prompt_text: string;
  source: 'manual' | 'suggestion' | 'ab_test';
  applied_suggestions?: string[] | null;
  accuracy_before?: number | null;
  accuracy_after?: number | null;
  camera_id?: string | null;
  created_at: string;
}

/**
 * Response from GET /api/v1/feedback/prompt-history
 */
export interface IPromptHistoryResponse {
  entries: IPromptHistoryEntry[];
  current_version: number;
  total_count: number;
}

// ==============================================================================
// Story P7-2.4: Package Delivery Dashboard Widget Types
// ==============================================================================

/**
 * Known delivery carriers for package detection
 */
export type DeliveryCarrier = 'fedex' | 'ups' | 'usps' | 'amazon' | 'dhl' | 'unknown';

/**
 * Summary of a package delivery event for the dashboard widget
 */
export interface IPackageEventSummary {
  id: string;                       // Event UUID
  timestamp: string;                // ISO 8601 datetime
  delivery_carrier: string | null;  // Carrier code (fedex, ups, etc.)
  delivery_carrier_display: string; // Human-readable carrier name
  camera_name: string;              // Camera that detected the package
  thumbnail_path: string | null;    // Relative path to thumbnail
}

/**
 * Response from GET /api/v1/events/packages/today
 */
export interface IPackageDeliveriesTodayResponse {
  total_count: number;                    // Total package deliveries today
  by_carrier: Record<string, number>;     // Count by carrier code
  recent_events: IPackageEventSummary[];  // Recent 5 package events
}

/**
 * Carrier display configuration for badges
 */
export const CARRIER_CONFIG: Record<string, { display: string; color: string; bgColor: string }> = {
  fedex: { display: 'FedEx', color: 'text-purple-700', bgColor: 'bg-purple-100' },
  ups: { display: 'UPS', color: 'text-amber-800', bgColor: 'bg-amber-100' },
  usps: { display: 'USPS', color: 'text-blue-700', bgColor: 'bg-blue-100' },
  amazon: { display: 'Amazon', color: 'text-orange-700', bgColor: 'bg-orange-100' },
  dhl: { display: 'DHL', color: 'text-yellow-700', bgColor: 'bg-yellow-100' },
  unknown: { display: 'Unknown', color: 'text-gray-600', bgColor: 'bg-gray-100' },
};

// ==============================================================================
// Story P8-2.2: Event Frame Gallery Types
// ==============================================================================

/**
 * Response for a single event frame
 * Matches backend EventFrameResponse schema
 */
export interface IEventFrame {
  id: string;                     // Frame UUID
  event_id: string;               // Parent event UUID
  frame_number: number;           // 1-indexed frame number
  frame_path: string;             // Relative path to frame file
  timestamp_offset_ms: number;    // Milliseconds from video start
  width: number | null;           // Frame width in pixels
  height: number | null;          // Frame height in pixels
  file_size_bytes: number | null; // Frame file size in bytes
  created_at: string;             // ISO 8601 datetime
  url: string;                    // URL to access the frame image
}

/**
 * Response from GET /api/v1/events/{event_id}/frames
 */
export interface IEventFramesResponse {
  event_id: string;               // Parent event UUID
  frames: IEventFrame[];          // List of frames
  total_count: number;            // Total number of frames
  total_size_bytes: number;       // Total size of all frames in bytes
}

// ==============================================================================
// Story P9-3.4: Summary Feedback Types
// ==============================================================================

/**
 * Summary Feedback interface for user ratings on activity summaries
 */
export interface ISummaryFeedback {
  id: string;                     // Feedback UUID
  summary_id: string;             // Summary UUID
  rating: 'positive' | 'negative';  // User rating
  correction_text: string | null; // Optional correction text
  created_at: string;             // ISO 8601 datetime
  updated_at?: string | null;     // ISO 8601 datetime
}
