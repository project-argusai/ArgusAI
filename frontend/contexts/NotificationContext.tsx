/**
 * Notification context for managing system notifications (Story 5.4)
 * Integrates with backend API and WebSocket for real-time notifications
 */

'use client';

import { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient, hasAuthToken } from '@/lib/api-client';
import { useWebSocket, ConnectionStatus } from '@/lib/hooks/useWebSocket';
import type { INotification } from '@/types/notification';

interface NotificationContextType {
  /** Notifications from backend */
  notifications: INotification[];
  /** Number of unread notifications */
  unreadCount: number;
  /** Total notification count */
  totalCount: number;
  /** Whether notifications are loading */
  isLoading: boolean;
  /** WebSocket connection status */
  connectionStatus: ConnectionStatus;
  /** Mark a single notification as read */
  markAsRead: (id: string) => Promise<void>;
  /** Mark all notifications as read */
  markAllAsRead: () => Promise<void>;
  /** Delete a notification */
  deleteNotification: (id: string) => Promise<void>;
  /** Refresh notifications from server */
  refetch: () => void;
}

const NotificationContext = createContext<NotificationContextType | undefined>(undefined);

const NOTIFICATIONS_QUERY_KEY = ['notifications'];

export function NotificationProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected');
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  // Check auth status on mount and when storage changes
  useEffect(() => {
    const checkAuth = () => setIsAuthenticated(hasAuthToken());
    checkAuth();

    // Listen for storage changes (login/logout in other tabs)
    window.addEventListener('storage', checkAuth);
    // Also check periodically in case of same-tab login
    const interval = setInterval(checkAuth, 1000);

    return () => {
      window.removeEventListener('storage', checkAuth);
      clearInterval(interval);
    };
  }, []);

  // Fetch notifications from API (only when authenticated)
  const {
    data: notificationData,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: NOTIFICATIONS_QUERY_KEY,
    queryFn: () => apiClient.notifications.list({ limit: 20 }),
    enabled: isAuthenticated, // Only fetch when authenticated
    refetchInterval: 60000, // Refetch every minute as fallback
    staleTime: 30000, // Consider data stale after 30 seconds
    retry: false, // Don't retry on 401
  });

  // Mark single as read mutation
  const markAsReadMutation = useMutation({
    mutationFn: (id: string) => apiClient.notifications.markRead(Number(id)),
    onMutate: async (id) => {
      // Optimistically update the cache
      queryClient.setQueryData(NOTIFICATIONS_QUERY_KEY, (old: typeof notificationData) => {
        if (!old) return old;
        return {
          ...old,
          data: old.data.map((n) =>
            n.id === id ? { ...n, read: true } : n
          ),
          unread_count: Math.max(0, old.unread_count - 1),
        };
      });
    },
    onSettled: () => {
      // Refetch to ensure consistency
      queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY });
    },
  });

  // Mark all as read mutation
  const markAllAsReadMutation = useMutation({
    mutationFn: () => apiClient.notifications.markAllRead(),
    onSuccess: () => {
      // Optimistically update the cache
      queryClient.setQueryData(NOTIFICATIONS_QUERY_KEY, (old: typeof notificationData) => {
        if (!old) return old;
        return {
          ...old,
          data: old.data.map((n) => ({ ...n, read: true })),
          unread_count: 0,
        };
      });
    },
  });

  // Delete notification mutation
  const deleteNotificationMutation = useMutation({
    mutationFn: (id: string) => apiClient.notifications.delete(Number(id)),
    onSuccess: (_, deletedId) => {
      // Remove from cache
      queryClient.setQueryData(NOTIFICATIONS_QUERY_KEY, (old: typeof notificationData) => {
        if (!old) return old;
        const deletedNotification = old.data.find((n) => n.id === deletedId);
        return {
          ...old,
          data: old.data.filter((n) => n.id !== deletedId),
          total_count: old.total_count - 1,
          unread_count: deletedNotification && !deletedNotification.read
            ? old.unread_count - 1
            : old.unread_count,
        };
      });
    },
  });

  // Handle new notification from WebSocket
  const handleNewNotification = useCallback((notification: INotification) => {
    queryClient.setQueryData(NOTIFICATIONS_QUERY_KEY, (old: typeof notificationData) => {
      if (!old) {
        return {
          data: [notification],
          total_count: 1,
          unread_count: 1,
        };
      }

      // Check if notification already exists
      if (old.data.some((n) => n.id === notification.id)) {
        return old;
      }

      return {
        ...old,
        data: [notification, ...old.data].slice(0, 20), // Keep max 20
        total_count: old.total_count + 1,
        unread_count: old.unread_count + 1,
      };
    });
  }, [queryClient]);

  // WebSocket connection
  useWebSocket({
    autoConnect: true,
    onNotification: handleNewNotification,
    onStatusChange: setConnectionStatus,
    onAlert: () => {
      // ALERT_TRIGGERED messages are legacy - refetch to get new notifications
      refetch();
    },
  });

  // Exposed functions
  const markAsRead = useCallback(async (id: string) => {
    await markAsReadMutation.mutateAsync(id);
  }, [markAsReadMutation]);

  const markAllAsRead = useCallback(async () => {
    await markAllAsReadMutation.mutateAsync();
  }, [markAllAsReadMutation]);

  const deleteNotification = useCallback(async (id: string) => {
    await deleteNotificationMutation.mutateAsync(id);
  }, [deleteNotificationMutation]);

  return (
    <NotificationContext.Provider
      value={{
        notifications: notificationData?.data ?? [],
        unreadCount: notificationData?.unread_count ?? 0,
        totalCount: notificationData?.total_count ?? 0,
        isLoading,
        connectionStatus,
        markAsRead,
        markAllAsRead,
        deleteNotification,
        refetch,
      }}
    >
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotifications() {
  const context = useContext(NotificationContext);
  if (context === undefined) {
    throw new Error('useNotifications must be used within a NotificationProvider');
  }
  return context;
}
