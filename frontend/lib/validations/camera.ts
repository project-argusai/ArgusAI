/**
 * Zod validation schemas for camera forms
 */

import { z } from 'zod';

/**
 * Detection zone vertex schema
 * Coordinates normalized to 0-1 scale
 */
export const zoneVertexSchema = z.object({
  x: z.number().min(0).max(1),
  y: z.number().min(0).max(1),
});

/**
 * Detection zone polygon schema
 * Validates minimum 3 vertices, coordinate bounds, required fields
 */
export const detectionZoneSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1).max(100),
  vertices: z.array(zoneVertexSchema).min(3, 'Polygon must have at least 3 vertices'),
  enabled: z.boolean(),
});

/**
 * Time range schema for individual time windows
 */
export const timeRangeSchema = z.object({
  start_time: z.string().regex(/^\d{2}:\d{2}$/, 'Start time must be in HH:MM format'),
  end_time: z.string().regex(/^\d{2}:\d{2}$/, 'End time must be in HH:MM format'),
});

/**
 * Check if two time ranges overlap (excluding adjacent ranges)
 * Handles both regular and overnight ranges
 */
function doRangesOverlap(range1: { start_time: string; end_time: string }, range2: { start_time: string; end_time: string }): boolean {
  // For adjacent ranges (one ends exactly when another starts), no overlap
  if (range1.end_time === range2.start_time || range2.end_time === range1.start_time) {
    return false;
  }

  // Handle overnight ranges (start > end)
  const isOvernight1 = range1.start_time > range1.end_time;
  const isOvernight2 = range2.start_time > range2.end_time;

  // If both are overnight ranges, they overlap (both cover midnight)
  if (isOvernight1 && isOvernight2) {
    return true;
  }

  // If one is overnight and one is regular, check for overlap
  if (isOvernight1 || isOvernight2) {
    const overnight = isOvernight1 ? range1 : range2;
    const regular = isOvernight1 ? range2 : range1;

    // Overnight range covers start_time to 23:59 AND 00:00 to end_time
    // Regular range overlaps if it touches either part
    const overlapsEveningPart = regular.start_time < '23:59' && regular.end_time > overnight.start_time;
    const overlapsMorningPart = regular.start_time < overnight.end_time;

    return overlapsEveningPart || overlapsMorningPart;
  }

  // Both are regular ranges - simple overlap check
  return range1.start_time < range2.end_time && range2.start_time < range1.end_time;
}

/**
 * Detection schedule schema with multiple time ranges support
 * Validates time format, days array, and overlap detection
 * Supports both new format (time_ranges) and legacy format (start_time/end_time)
 */
export const detectionScheduleSchema = z.object({
  enabled: z.boolean(),
  // New format: array of time ranges (preferred)
  time_ranges: z.array(timeRangeSchema)
    .max(4, 'Maximum 4 time ranges per schedule')
    .optional(),
  days: z.array(z.number().int().min(0).max(6)).min(1, 'At least one day must be selected'),
  // Legacy fields for backward compatibility
  start_time: z.string().regex(/^\d{2}:\d{2}$/, 'Start time must be in HH:MM format').optional(),
  end_time: z.string().regex(/^\d{2}:\d{2}$/, 'End time must be in HH:MM format').optional(),
}).refine(
  (data) => {
    // Must have either time_ranges or legacy start_time/end_time
    const hasTimeRanges = data.time_ranges && data.time_ranges.length > 0;
    const hasLegacyFormat = data.start_time && data.end_time;
    return hasTimeRanges || hasLegacyFormat;
  },
  {
    message: 'At least one time range is required',
    path: ['time_ranges'],
  }
).refine(
  (data) => {
    // Check for overlapping ranges (only if using new format)
    const ranges = data.time_ranges;
    if (!ranges || ranges.length <= 1) return true;

    for (let i = 0; i < ranges.length; i++) {
      for (let j = i + 1; j < ranges.length; j++) {
        if (doRangesOverlap(ranges[i], ranges[j])) {
          return false;
        }
      }
    }
    return true;
  },
  {
    message: 'Time ranges cannot overlap. Please adjust the times or remove overlapping ranges.',
    path: ['time_ranges'],
  }
);

/**
 * Camera form schema with conditional validation
 * Mirrors backend Pydantic validation rules
 */
export const cameraFormSchema = z.object({
  name: z
    .string()
    .min(1, 'Camera name is required')
    .max(100, 'Camera name must be 100 characters or less'),

  type: z.enum(['rtsp', 'usb']),

  // RTSP fields (conditional)
  rtsp_url: z.string().optional().nullable(),
  username: z.string().max(100).optional().nullable(),
  password: z.string().max(100).optional().nullable(),

  // USB fields (conditional)
  device_index: z.number().int().min(0).optional().nullable(),

  // Common fields (with defaults in defaultValues, not Zod schema)
  frame_rate: z.number().int().min(1).max(30),
  is_enabled: z.boolean(),
  motion_enabled: z.boolean(),
  motion_sensitivity: z.enum(['low', 'medium', 'high']),
  motion_cooldown: z.number().int().min(5).max(300),
  motion_algorithm: z.enum(['mog2', 'knn', 'frame_diff']),
  detection_zones: z.array(detectionZoneSchema).max(10, 'Maximum 10 zones per camera').optional(),
  detection_schedule: detectionScheduleSchema.optional().nullable(),
  // Phase 3: AI analysis mode
  analysis_mode: z.enum(['single_frame', 'multi_frame', 'video_native']),
}).superRefine((data, ctx) => {
  // Validate RTSP-specific fields
  if (data.type === 'rtsp') {
    if (!data.rtsp_url) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'RTSP URL is required for RTSP cameras',
        path: ['rtsp_url'],
      });
    } else if (!data.rtsp_url.startsWith('rtsp://') && !data.rtsp_url.startsWith('rtsps://')) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'RTSP URL must start with rtsp:// or rtsps://',
        path: ['rtsp_url'],
      });
    }
  }

  // Validate USB-specific fields
  if (data.type === 'usb') {
    if (data.device_index === undefined || data.device_index === null) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Device index is required for USB cameras',
        path: ['device_index'],
      });
    }
  }
});

export type CameraFormValues = z.infer<typeof cameraFormSchema>;
