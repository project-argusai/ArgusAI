/**
 * WebSocket hook for real-time notifications (Story 5.4)
 * Updated for Story P2-2.4: Camera status change handling
 *
 * Provides:
 * - Auto-connect on mount
 * - Reconnect with exponential backoff on disconnect
 * - Heartbeat/ping handling
 * - Connection status tracking
 * - Camera status change notifications (Story P2-2.4)
 */

'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import type { WebSocketMessage, IWebSocketNotification } from '@/types/notification';

// Derive WebSocket URL from API URL or use explicit WS URL
const getWebSocketBaseUrl = (): string => {
  // Use explicit WS URL if set
  if (process.env.NEXT_PUBLIC_WS_URL) {
    return process.env.NEXT_PUBLIC_WS_URL;
  }

  // Derive from API URL if set
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (apiUrl) {
    // Convert http(s):// to ws(s)://
    return apiUrl.replace(/^http/, 'ws');
  }

  // Fall back to window location (for relative API URLs)
  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Use same port as the page is served from (frontend handles proxying)
    return `${protocol}//${window.location.host}`;
  }

  return 'ws://localhost:8000';
};

const WS_BASE_URL = getWebSocketBaseUrl();

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'reconnecting';

/** Camera status change data (Story P2-2.4 AC7) */
export interface CameraStatusChangeData {
  controller_id: string;
  camera_id: string;
  is_online: boolean;
}

interface UseWebSocketOptions {
  /** Callback when notification received */
  onNotification?: (notification: IWebSocketNotification['data']) => void;
  /** Callback when alert triggered */
  onAlert?: (data: { event: Record<string, unknown>; rule: Record<string, unknown> }) => void;
  /** Callback when new event is created */
  onNewEvent?: (data: { event_id: string; camera_id: string; description: string | null }) => void;
  /** Callback when camera status changes (Story P2-2.4 AC1, AC8) */
  onCameraStatusChange?: (data: CameraStatusChangeData) => void;
  /** Callback on connection status change */
  onStatusChange?: (status: ConnectionStatus) => void;
  /** Auto-connect on mount (default: true) */
  autoConnect?: boolean;
  /** Max reconnection attempts (default: 10) */
  maxRetries?: number;
}

interface UseWebSocketReturn {
  /** Current connection status */
  status: ConnectionStatus;
  /** Manually connect */
  connect: () => void;
  /** Manually disconnect */
  disconnect: () => void;
  /** Send a message */
  send: (message: string) => void;
}

// Exponential backoff delays in ms: 1s, 2s, 4s, 8s, 16s, 30s (capped)
const getBackoffDelay = (attempt: number): number => {
  const baseDelay = 1000;
  const maxDelay = 30000;
  return Math.min(baseDelay * Math.pow(2, attempt), maxDelay);
};

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const {
    onNotification,
    onAlert,
    onNewEvent,
    onCameraStatusChange,
    onStatusChange,
    autoConnect = true,
    maxRetries = 10,
  } = options;

  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const shouldReconnectRef = useRef(true);

  // Store callbacks in refs to avoid dependency issues
  const onNotificationRef = useRef(onNotification);
  const onAlertRef = useRef(onAlert);
  const onNewEventRef = useRef(onNewEvent);
  const onCameraStatusChangeRef = useRef(onCameraStatusChange);
  const onStatusChangeRef = useRef(onStatusChange);

  // Update refs when callbacks change
  useEffect(() => {
    onNotificationRef.current = onNotification;
    onAlertRef.current = onAlert;
    onNewEventRef.current = onNewEvent;
    onCameraStatusChangeRef.current = onCameraStatusChange;
    onStatusChangeRef.current = onStatusChange;
  }, [onNotification, onAlert, onNewEvent, onCameraStatusChange, onStatusChange]);

  // Update status and notify callback
  const updateStatus = useCallback((newStatus: ConnectionStatus) => {
    setStatus(newStatus);
    onStatusChangeRef.current?.(newStatus);
  }, []);

  // Handle incoming messages
  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      // Handle text-based ping/pong
      if (event.data === 'ping') {
        wsRef.current?.send('pong');
        return;
      }
      if (event.data === 'pong') {
        return;
      }

      // Parse JSON messages
      const message: WebSocketMessage = JSON.parse(event.data);

      if (message.type === 'notification') {
        onNotificationRef.current?.(message.data);
      } else if (message.type === 'ALERT_TRIGGERED') {
        onAlertRef.current?.(message.data);
      } else if (message.type === 'NEW_EVENT') {
        onNewEventRef.current?.(message.data);
      } else if (message.type === 'CAMERA_STATUS_CHANGED') {
        // Story P2-2.4 AC1, AC8: Handle camera status change
        onCameraStatusChangeRef.current?.(message.data as CameraStatusChangeData);
      }
    } catch (error) {
      console.warn('Failed to parse WebSocket message:', error);
    }
  }, []);

  // Connect to WebSocket - uses refs for values that change
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    // Clean up existing connection
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    shouldReconnectRef.current = true;
    updateStatus('connecting');

    const attemptConnect = () => {
      try {
        const ws = new WebSocket(`${WS_BASE_URL}/ws`);

        ws.onopen = () => {
          console.log('WebSocket connected');
          updateStatus('connected');
          reconnectAttemptRef.current = 0;
        };

        ws.onclose = (event) => {
          console.log('WebSocket closed:', event.code, event.reason);
          wsRef.current = null;

          if (shouldReconnectRef.current && reconnectAttemptRef.current < maxRetries) {
            updateStatus('reconnecting');
            const delay = getBackoffDelay(reconnectAttemptRef.current);
            console.log(`Reconnecting in ${delay}ms (attempt ${reconnectAttemptRef.current + 1}/${maxRetries})`);

            reconnectTimeoutRef.current = setTimeout(() => {
              reconnectAttemptRef.current++;
              attemptConnect();
            }, delay);
          } else {
            updateStatus('disconnected');
            if (reconnectAttemptRef.current >= maxRetries) {
              console.warn('Max WebSocket reconnection attempts reached');
            }
          }
        };

        ws.onerror = () => {
          // WebSocket errors don't expose details for security reasons
          // The onclose handler will manage reconnection
          console.warn('WebSocket connection error (backend may be unavailable)');
        };

        ws.onmessage = handleMessage;

        wsRef.current = ws;
      } catch (error) {
        console.error('Failed to create WebSocket:', error);
        updateStatus('disconnected');
      }
    };

    attemptConnect();
  }, [handleMessage, maxRetries, updateStatus]);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    shouldReconnectRef.current = false;

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    updateStatus('disconnected');
  }, [updateStatus]);

  // Send a message
  const send = useCallback((message: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(message);
    } else {
      console.warn('WebSocket not connected, cannot send message');
    }
  }, []);

  // Auto-connect on mount and cleanup on unmount
  // Using setTimeout(0) to defer to avoid lint warning about synchronous setState in effects
  useEffect(() => {
    let mounted = true;
    let connectTimeout: NodeJS.Timeout | null = null;

    if (autoConnect) {
      // Defer connection to next tick to avoid synchronous setState in effect
      connectTimeout = setTimeout(() => {
        if (mounted) {
          connect();
        }
      }, 0);
    }

    return () => {
      mounted = false;
      if (connectTimeout) {
        clearTimeout(connectTimeout);
      }
      shouldReconnectRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [autoConnect, connect]);

  return {
    status,
    connect,
    disconnect,
    send,
  };
}
