/**
 * Alert Rule TypeScript types
 * Matches backend Pydantic schemas from backend/app/schemas/alert_rule.py
 */

// Time of day range for conditions
export interface ITimeOfDay {
  start: string; // HH:MM format (24-hour)
  end: string;   // HH:MM format (24-hour)
}

// Webhook configuration for actions
export interface IWebhookConfig {
  url: string;
  headers?: Record<string, string>;
}

// Alert rule conditions (AND logic between conditions, OR logic within object_types)
export interface IAlertRuleConditions {
  rule_type?: string;           // 'any' (default) or 'package_delivery' (Story P7-2.2)
  carriers?: string[];          // Carrier filter for package_delivery: fedex, ups, usps, amazon, dhl (Story P7-2.2)
  object_types?: string[];      // Valid: person, vehicle, animal, package, unknown
  cameras?: string[];           // Camera UUIDs, empty = any camera
  time_of_day?: ITimeOfDay;     // Optional time range
  days_of_week?: number[];      // 1=Monday, 7=Sunday
  min_confidence?: number;      // 0-100
}

// Alert rule actions
export interface IAlertRuleActions {
  dashboard_notification?: boolean;
  webhook?: IWebhookConfig;
}

// Full alert rule response from API
export interface IAlertRule {
  id: string;
  name: string;
  is_enabled: boolean;
  conditions: IAlertRuleConditions;
  actions: IAlertRuleActions;
  cooldown_minutes: number;
  last_triggered_at: string | null;
  trigger_count: number;
  created_at: string;
  updated_at: string;
}

// Create alert rule request
export interface IAlertRuleCreate {
  name: string;
  is_enabled?: boolean;
  conditions?: IAlertRuleConditions;
  actions?: IAlertRuleActions;
  cooldown_minutes?: number;
}

// Update alert rule request (partial)
export interface IAlertRuleUpdate {
  name?: string;
  is_enabled?: boolean;
  conditions?: IAlertRuleConditions;
  actions?: IAlertRuleActions;
  cooldown_minutes?: number;
}

// List response with pagination
export interface IAlertRuleListResponse {
  data: IAlertRule[];
  total_count: number;
}

// Test rule request
export interface IAlertRuleTestRequest {
  limit?: number; // 1-100, default 50
}

// Test rule response
export interface IAlertRuleTestResponse {
  rule_id: string;
  events_tested: number;
  events_matched: number;
  matching_event_ids: string[];
}

// Valid object types for UI
export const OBJECT_TYPES = ['person', 'vehicle', 'animal', 'package', 'unknown'] as const;
export type ObjectType = typeof OBJECT_TYPES[number];

// Story P7-2.2: Rule types for alert rules
export const RULE_TYPES = [
  { value: 'any', label: 'Any Detection', description: 'Match any detection type (default)' },
  { value: 'package_delivery', label: 'Package Delivery', description: 'Match package deliveries with carrier identification' },
] as const;
export type RuleType = typeof RULE_TYPES[number]['value'];

// Story P7-2.2: Delivery carriers for package delivery rules
export const CARRIERS = [
  { value: 'fedex', label: 'FedEx' },
  { value: 'ups', label: 'UPS' },
  { value: 'usps', label: 'USPS' },
  { value: 'amazon', label: 'Amazon' },
  { value: 'dhl', label: 'DHL' },
] as const;
export type Carrier = typeof CARRIERS[number]['value'];

// Days of week for UI
export const DAYS_OF_WEEK = [
  { value: 1, label: 'Mon', fullLabel: 'Monday' },
  { value: 2, label: 'Tue', fullLabel: 'Tuesday' },
  { value: 3, label: 'Wed', fullLabel: 'Wednesday' },
  { value: 4, label: 'Thu', fullLabel: 'Thursday' },
  { value: 5, label: 'Fri', fullLabel: 'Friday' },
  { value: 6, label: 'Sat', fullLabel: 'Saturday' },
  { value: 7, label: 'Sun', fullLabel: 'Sunday' },
] as const;

// ============================================================================
// Webhook Types (Story 5.3)
// ============================================================================

// Webhook test request
export interface IWebhookTestRequest {
  url: string;
  headers?: Record<string, string>;
  payload?: Record<string, unknown>;
}

// Webhook test response
export interface IWebhookTestResponse {
  success: boolean;
  status_code: number;
  response_body: string;
  response_time_ms: number;
  error?: string;
}

// Single webhook log entry
export interface IWebhookLog {
  id: number;
  alert_rule_id: string;
  rule_name?: string;
  event_id: string;
  url: string;
  status_code: number;
  response_time_ms: number;
  retry_count: number;
  success: boolean;
  error_message?: string;
  created_at: string;
}

// Webhook logs list response
export interface IWebhookLogsResponse {
  data: IWebhookLog[];
  total_count: number;
}

// Webhook logs filter parameters
export interface IWebhookLogsFilter {
  rule_id?: string;
  success?: boolean;
  start_date?: string;
  end_date?: string;
  limit?: number;
  offset?: number;
}
