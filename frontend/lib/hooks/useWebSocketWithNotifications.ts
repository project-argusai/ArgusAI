/**
 * WebSocket hook with toast notifications for connection state changes
 * Story P2-6.3: Phase 2 Error Handling
 *
 * AC8: WebSocket connection lost shows yellow toast with auto-reconnect
 * AC9: WebSocket reconnected shows brief green toast
 * AC10: Max WebSocket retries exceeded shows red banner with manual reconnect option
 *
 * Wraps useWebSocket with toast notifications for connection state changes
 */

'use client';

import { useCallback, useRef, useEffect, useState } from 'react';
import { toast } from 'sonner';
import {
  useWebSocket,
  type ConnectionStatus,
  type CameraStatusChangeData,
} from './useWebSocket';
import type { IWebSocketNotification } from '@/types/notification';

interface UseWebSocketWithNotificationsOptions {
  /** Callback when notification received */
  onNotification?: (notification: IWebSocketNotification['data']) => void;
  /** Callback when alert triggered */
  onAlert?: (data: { event: Record<string, unknown>; rule: Record<string, unknown> }) => void;
  /** Callback when new event is created */
  onNewEvent?: (data: { event_id: string; camera_id: string; description: string | null }) => void;
  /** Callback when camera status changes */
  onCameraStatusChange?: (data: CameraStatusChangeData) => void;
  /** Auto-connect on mount (default: true) */
  autoConnect?: boolean;
  /** Max reconnection attempts (default: 10) */
  maxRetries?: number;
  /** Show toast notifications for connection state changes (default: true) */
  showToasts?: boolean;
}

interface UseWebSocketWithNotificationsReturn {
  /** Current connection status */
  status: ConnectionStatus;
  /** Whether max retries has been exceeded */
  maxRetriesExceeded: boolean;
  /** Manually connect */
  connect: () => void;
  /** Manually disconnect */
  disconnect: () => void;
  /** Send a message */
  send: (message: string) => void;
}

/**
 * WebSocket hook with toast notifications
 *
 * Provides all the functionality of useWebSocket plus:
 * - Yellow toast when connection is lost with auto-reconnect in progress
 * - Green toast when reconnection succeeds
 * - Tracks max retries exceeded state for showing manual reconnect UI
 */
export function useWebSocketWithNotifications(
  options: UseWebSocketWithNotificationsOptions = {}
): UseWebSocketWithNotificationsReturn {
  const {
    onNotification,
    onAlert,
    onNewEvent,
    onCameraStatusChange,
    autoConnect = true,
    maxRetries = 10,
    showToasts = true,
  } = options;

  // Track previous status to detect transitions
  const previousStatusRef = useRef<ConnectionStatus>('disconnected');
  const [maxRetriesExceeded, setMaxRetriesExceeded] = useState(false);
  const [authFailureMessage, setAuthFailureMessage] = useState<string | null>(null);
  const reconnectAttemptRef = useRef(0);

  // Toast IDs for dismissing
  const reconnectingToastIdRef = useRef<string | number | undefined>(undefined);

  // Handle status changes with toast notifications
  const handleStatusChange = useCallback(
    (newStatus: ConnectionStatus) => {
      const previousStatus = previousStatusRef.current;

      // Skip if status hasn't changed
      if (previousStatus === newStatus) {
        return;
      }

      // Detect state transitions and show appropriate toasts
      if (showToasts) {
        // Connected -> Reconnecting: Show yellow toast (AC8)
        if (authFailureMessage) {
          if (reconnectingToastIdRef.current) {
            toast.dismiss(reconnectingToastIdRef.current);
            reconnectingToastIdRef.current = undefined;
          }
          previousStatusRef.current = newStatus;
          return;
        }

        if (previousStatus === 'connected' && newStatus === 'reconnecting') {
          // Dismiss any existing reconnecting toast
          if (reconnectingToastIdRef.current) {
            toast.dismiss(reconnectingToastIdRef.current);
          }

          reconnectAttemptRef.current++;
          reconnectingToastIdRef.current = toast.warning(
            'Connection lost. Reconnecting...',
            {
              description: `Attempt ${reconnectAttemptRef.current}/${maxRetries}`,
              duration: Infinity, // Keep visible until reconnected or max retries
              id: 'websocket-reconnecting',
            }
          );
          setMaxRetriesExceeded(false);
        }

        // Reconnecting -> Reconnecting: Update attempt count
        if (previousStatus === 'reconnecting' && newStatus === 'reconnecting') {
          reconnectAttemptRef.current++;
          if (reconnectingToastIdRef.current) {
            toast.warning('Connection lost. Reconnecting...', {
              description: `Attempt ${reconnectAttemptRef.current}/${maxRetries}`,
              duration: Infinity,
              id: 'websocket-reconnecting',
            });
          }
        }

        // Reconnecting -> Connected: Show green toast (AC9)
        if (previousStatus === 'reconnecting' && newStatus === 'connected') {
          // Dismiss reconnecting toast
          if (reconnectingToastIdRef.current) {
            toast.dismiss(reconnectingToastIdRef.current);
            reconnectingToastIdRef.current = undefined;
          }

          toast.success('Reconnected', {
            description: 'WebSocket connection restored',
            duration: 3000, // Brief toast
          });
          reconnectAttemptRef.current = 0;
          setMaxRetriesExceeded(false);
        }

        // Reconnecting -> Disconnected (max retries exceeded) (AC10)
        if (previousStatus === 'reconnecting' && newStatus === 'disconnected') {
          // Dismiss reconnecting toast
          if (reconnectingToastIdRef.current) {
            toast.dismiss(reconnectingToastIdRef.current);
            reconnectingToastIdRef.current = undefined;
          }

          if (reconnectAttemptRef.current >= maxRetries) {
            toast.error('Connection failed', {
              description: 'Max reconnection attempts reached. Click to retry.',
              duration: Infinity, // Keep visible until user action
              action: {
                label: 'Reconnect',
                onClick: () => {
                  reconnectAttemptRef.current = 0;
                  setMaxRetriesExceeded(false);
                },
              },
            });
            setMaxRetriesExceeded(true);
          }
        }

        // Connecting -> Connected (initial connection)
        if (previousStatus === 'connecting' && newStatus === 'connected') {
          // Don't show toast for initial connection, only for reconnection
          reconnectAttemptRef.current = 0;
        }
      }

      previousStatusRef.current = newStatus;
    },
    [authFailureMessage, maxRetries, showToasts]
  );

  useEffect(() => {
    if (!showToasts || !authFailureMessage) {
      return;
    }
    toast.error('Live updates stopped', {
      description: authFailureMessage,
      id: 'websocket-auth-failure',
    });
  }, [authFailureMessage, showToasts]);

  const {
    status,
    connect: wsConnect,
    disconnect: wsDisconnect,
    send,
  } = useWebSocket({
    onNotification,
    onAlert,
    onNewEvent,
    onCameraStatusChange,
    onStatusChange: handleStatusChange,
    onAuthFailure: setAuthFailureMessage,
    autoConnect,
    maxRetries,
  });

  // Wrap connect to reset state
  const connect = useCallback(() => {
    reconnectAttemptRef.current = 0;
    setMaxRetriesExceeded(false);
    wsConnect();
  }, [wsConnect]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (reconnectingToastIdRef.current) {
        toast.dismiss(reconnectingToastIdRef.current);
      }
    };
  }, []);

  return {
    status,
    maxRetriesExceeded,
    connect,
    disconnect: wsDisconnect,
    send,
  };
}
