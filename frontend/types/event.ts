/**
 * Event-related TypeScript interfaces for Live Object AI Classifier
 */

/**
 * Main Event interface matching backend Event model
 */
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
