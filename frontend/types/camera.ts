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
  motion_sensitivity: MotionSensitivity;
  motion_cooldown: number;
  motion_algorithm: MotionAlgorithm;
  created_at: string; // ISO 8601 datetime
  updated_at: string; // ISO 8601 datetime
}

/**
 * Camera creation payload (matches backend CameraCreate)
 */
export interface ICameraCreate {
  name: string;
  type: CameraType;
  rtsp_url?: string;
  username?: string;
  password?: string;
  device_index?: number;
  frame_rate?: number;
  is_enabled?: boolean;
  motion_sensitivity?: MotionSensitivity;
  motion_cooldown?: number;
  motion_algorithm?: MotionAlgorithm;
}

/**
 * Camera update payload (matches backend CameraUpdate)
 * All fields optional for partial updates
 */
export interface ICameraUpdate {
  name?: string;
  rtsp_url?: string;
  username?: string;
  password?: string;
  frame_rate?: number;
  is_enabled?: boolean;
  motion_sensitivity?: MotionSensitivity;
  motion_cooldown?: number;
  motion_algorithm?: MotionAlgorithm;
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
