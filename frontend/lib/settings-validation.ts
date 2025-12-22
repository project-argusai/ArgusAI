/**
 * Settings Validation Schemas
 * Zod schemas for form validation across all settings tabs
 */

import { z } from 'zod';

// General Settings Schema
export const generalSettingsSchema = z.object({
  system_name: z
    .string()
    .min(1, 'System name is required')
    .max(100, 'System name must be less than 100 characters'),
  timezone: z.string().min(1, 'Timezone is required'),
  language: z.string().min(1, 'Language is required'),
  date_format: z.enum(['MM/DD/YYYY', 'DD/MM/YYYY', 'YYYY-MM-DD']),
  time_format: z.enum(['12h', '24h']),
  // Story P8-2.3: Configurable frame count for AI analysis
  analysis_frame_count: z.union([z.literal(5), z.literal(10), z.literal(15), z.literal(20)]).optional(),
  // Story P8-3.2: Full motion video storage
  store_motion_videos: z.boolean().optional(),
  video_retention_days: z.number().min(1).max(365).optional(),
  // Story P9-3.2: OCR frame overlay extraction
  attempt_ocr_extraction: z.boolean().optional(),
});

// AI Models Settings Schema
export const aiModelsSettingsSchema = z.object({
  primary_model: z.enum(['gpt-4o-mini', 'claude-3-haiku', 'gemini-flash']),
  primary_api_key: z.string().optional().default(''), // Optional - may already be saved on backend
  fallback_model: z
    .enum(['gpt-4o-mini', 'claude-3-haiku', 'gemini-flash'])
    .nullable()
    .optional(),
  description_prompt: z.string().min(10, 'Prompt must be at least 10 characters'),
  // Story P9-3.5: Summary Prompt Customization
  summary_prompt: z.string().max(2000, 'Summary prompt must be less than 2000 characters').optional(),
});

// Motion Detection Settings Schema
export const motionDetectionSettingsSchema = z.object({
  motion_sensitivity: z.number().min(0).max(100),
  detection_method: z.enum(['background_subtraction', 'frame_difference']),
  cooldown_period: z.number().min(30).max(300),
  min_motion_area: z.number().min(1).max(10),
  save_debug_images: z.boolean(),
});

// Data & Privacy Settings Schema
export const dataPrivacySettingsSchema = z.object({
  retention_days: z.number().int(),
  thumbnail_storage: z.enum(['filesystem', 'database']),
  auto_cleanup: z.boolean(),
});

// Complete Settings Schema (combination of all)
export const completeSettingsSchema = z.object({
  ...generalSettingsSchema.shape,
  ...aiModelsSettingsSchema.shape,
  ...motionDetectionSettingsSchema.shape,
  ...dataPrivacySettingsSchema.shape,
});

export type GeneralSettingsFormData = z.infer<typeof generalSettingsSchema>;
export type AIModelsSettingsFormData = z.infer<typeof aiModelsSettingsSchema>;
export type MotionDetectionSettingsFormData = z.infer<typeof motionDetectionSettingsSchema>;
export type DataPrivacySettingsFormData = z.infer<typeof dataPrivacySettingsSchema>;
export type CompleteSettingsFormData = z.infer<typeof completeSettingsSchema>;
