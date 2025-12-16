/**
 * TypeScript type definitions for Camera API
 * Mirrors backend Pydantic schemas from backend/app/schemas/camera.py
 */

/**
 * Camera type literal (legacy field)
 */
export type CameraType = 'rtsp' | 'usb';

/**
 * Camera source type (Phase 2: includes protect)
 */
export type CameraSourceType = 'rtsp' | 'usb' | 'protect';

/**
 * Motion sensitivity levels
 */
export type MotionSensitivity = 'low' | 'medium' | 'high';

/**
 * Motion detection algorithm options
 */
export type MotionAlgorithm = 'mog2' | 'knn' | 'frame_diff';

/**
 * AI analysis mode options (Phase 3)
 * - single_frame: Uses event thumbnail only (fastest, lowest cost)
 * - multi_frame: Extracts 5 frames from video clip (balanced)
 * - video_native: Sends full video to AI (best quality, highest cost, Protect only)
 */
export type AnalysisMode = 'single_frame' | 'multi_frame' | 'video_native';

/**
 * Detection zone vertex coordinate
 * Normalized to 0-1 scale relative to image dimensions
 */
export interface IZoneVertex {
  x: number; // 0-1 range
  y: number; // 0-1 range
}

/**
 * Detection zone polygon (matches backend DetectionZone schema)
 * Vertices normalized to 0-1 scale for responsive display
 */
export interface IDetectionZone {
  id: string;
  name: string;
  vertices: IZoneVertex[]; // Minimum 3 vertices for valid polygon
  enabled: boolean;
}

/**
 * Time range for detection schedule (Phase 5 - Story P5-5.4)
 * Represents a single active time window
 */
export interface ITimeRange {
  start_time: string; // Format: "HH:MM" (24-hour)
  end_time: string;   // Format: "HH:MM" (24-hour)
}

/**
 * Detection schedule configuration (matches backend DetectionSchedule schema)
 * Controls when motion detection is active based on time and day
 *
 * Supports multiple time ranges per day (Phase 5 - Story P5-5.4):
 * - time_ranges: Array of time windows (preferred, max 4 per day)
 * - start_time/end_time: Legacy single range format (backward compatibility)
 */
export interface IDetectionSchedule {
  enabled: boolean;
  time_ranges?: ITimeRange[];  // NEW: Array of time ranges (min 1, max 4)
  days: number[];              // 0-6 (Monday-Sunday per Python weekday())
  // Legacy fields for backward compatibility:
  start_time?: string;         // DEPRECATED: Use time_ranges instead
  end_time?: string;           // DEPRECATED: Use time_ranges instead
}

/**
 * Complete camera object (matches backend CameraResponse)
 */
export interface ICamera {
  id: string;
  name: string;
  type: CameraType;
  rtsp_url?: string;
  username?: string;
  device_index?: number;
  frame_rate: number;
  is_enabled: boolean;
  motion_enabled: boolean; // Whether motion detection is active
  motion_sensitivity: MotionSensitivity;
  motion_cooldown: number;
  motion_algorithm: MotionAlgorithm;
  detection_zones?: IDetectionZone[] | null; // Optional array of detection zones (max 10)
  detection_schedule?: IDetectionSchedule | null; // Optional detection schedule configuration
  // Phase 3: AI analysis mode
  analysis_mode: AnalysisMode; // AI analysis mode for event processing
  // Phase 2: UniFi Protect integration fields
  source_type: CameraSourceType; // 'rtsp', 'usb', or 'protect'
  protect_controller_id?: string | null; // Foreign key to protect_controllers
  protect_camera_id?: string | null; // Native Protect camera ID
  protect_camera_type?: string | null; // Protect camera type/model (e.g., "G4 Doorbell Pro")
  smart_detection_types?: string[] | null; // JSON array: ["person", "vehicle", "package", "animal"]
  is_doorbell?: boolean; // Whether camera is a doorbell
  created_at: string; // ISO 8601 datetime
  updated_at: string; // ISO 8601 datetime
}

/**
 * Camera creation payload (matches backend CameraCreate)
 */
export interface ICameraCreate {
  name: string;
  type: CameraType;
  rtsp_url?: string | null;
  username?: string | null;
  password?: string | null;
  device_index?: number | null;
  frame_rate?: number;
  is_enabled?: boolean;
  motion_enabled?: boolean;
  motion_sensitivity?: MotionSensitivity;
  motion_cooldown?: number;
  motion_algorithm?: MotionAlgorithm;
  detection_zones?: IDetectionZone[];
  detection_schedule?: IDetectionSchedule | null;
  analysis_mode?: AnalysisMode; // Phase 3: AI analysis mode
}

/**
 * Camera update payload (matches backend CameraUpdate)
 * All fields optional for partial updates
 */
export interface ICameraUpdate {
  name?: string;
  rtsp_url?: string | null;
  username?: string | null;
  password?: string | null;
  frame_rate?: number;
  is_enabled?: boolean;
  motion_enabled?: boolean;
  motion_sensitivity?: MotionSensitivity;
  motion_cooldown?: number;
  motion_algorithm?: MotionAlgorithm;
  device_index?: number | null;
  detection_zones?: IDetectionZone[];
  detection_schedule?: IDetectionSchedule | null;
  analysis_mode?: AnalysisMode; // Phase 3: AI analysis mode
}

/**
 * Camera connection test response (matches backend CameraTestResponse)
 */
export interface ICameraTestResponse {
  success: boolean;
  message: string;
  thumbnail?: string; // Base64-encoded JPEG with data URI prefix
}

/**
 * API error response structure
 */
export interface IApiError {
  detail: string;
  status_code?: number;
  errors?: Array<{
    field: string;
    message: string;
  }>;
}
