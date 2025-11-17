/**
 * TypeScript type definitions for Camera API
 * Mirrors backend Pydantic schemas from backend/app/schemas/camera.py
 */

/**
 * Camera type literal
 */
export type CameraType = 'rtsp' | 'usb';

/**
 * Motion sensitivity levels
 */
export type MotionSensitivity = 'low' | 'medium' | 'high';

/**
 * Motion detection algorithm options
 */
export type MotionAlgorithm = 'mog2' | 'knn' | 'frame_diff';

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
 * Detection schedule configuration (matches backend DetectionSchedule schema)
 * Controls when motion detection is active based on time and day
 */
export interface IDetectionSchedule {
  enabled: boolean;
  start_time: string; // Format: "HH:MM" (24-hour)
  end_time: string;   // Format: "HH:MM" (24-hour)
  days: number[];     // 0-6 (Monday-Sunday per Python weekday())
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
