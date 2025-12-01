/**
 * Notification types for the dashboard notification center (Story 5.4)
 */

/**
 * Backend notification record from API
 */
export interface INotification {
  id: string;
  event_id: string;
  rule_id: string;
  rule_name: string;
  event_description: string | null;
  thumbnail_url: string | null;
  read: boolean;
  created_at: string;
}

/**
 * Response from GET /api/v1/notifications
 */
export interface INotificationListResponse {
  data: INotification[];
  total_count: number;
  unread_count: number;
}

/**
 * Response from PATCH /api/v1/notifications/mark-all-read
 */
export interface IMarkReadResponse {
  success: boolean;
  updated_count: number;
}

/**
 * Response from DELETE /api/v1/notifications/:id
 */
export interface IDeleteNotificationResponse {
  deleted: boolean;
  id: string;
}

/**
 * Response from DELETE /api/v1/notifications (bulk delete)
 */
export interface IBulkDeleteResponse {
  deleted: boolean;
  count: number;
}

/**
 * WebSocket notification message payload
 */
export interface IWebSocketNotification {
  type: 'notification';
  data: INotification;
  timestamp: string;
}

/**
 * WebSocket new event message payload
 */
export interface IWebSocketNewEvent {
  type: 'NEW_EVENT';
  data: {
    event_id: string;
    camera_id: string;
    description: string | null;
  };
  timestamp: string;
}

/**
 * WebSocket camera status change message payload (Story P2-2.4)
 */
export interface IWebSocketCameraStatusChange {
  type: 'CAMERA_STATUS_CHANGED';
  data: {
    controller_id: string;
    camera_id: string;
    is_online: boolean;
  };
  timestamp: string;
}

/**
 * WebSocket message types
 */
export type WebSocketMessage =
  | IWebSocketNotification
  | IWebSocketNewEvent
  | IWebSocketCameraStatusChange
  | { type: 'ping' | 'pong' }
  | { type: 'ALERT_TRIGGERED'; data: { event: Record<string, unknown>; rule: Record<string, unknown> }; timestamp: string };
