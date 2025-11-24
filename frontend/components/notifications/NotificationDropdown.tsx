/**
 * Notification dropdown panel (Story 5.4)
 *
 * Displays recent notifications with:
 * - Thumbnail, title, description, timestamp
 * - Read/unread visual states
 * - Mark all as read button
 * - Click to navigate to event
 */

'use client';

import { useRouter } from 'next/navigation';
import { formatDistanceToNow } from 'date-fns';
import { Check, Trash2, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { useNotifications } from '@/contexts/NotificationContext';
import type { INotification } from '@/types/notification';

interface NotificationDropdownProps {
  onClose?: () => void;
}

export function NotificationDropdown({ onClose }: NotificationDropdownProps) {
  const router = useRouter();
  const {
    notifications,
    unreadCount,
    isLoading,
    markAsRead,
    markAllAsRead,
    deleteNotification,
  } = useNotifications();

  const handleNotificationClick = async (notification: INotification) => {
    // Mark as read if unread
    if (!notification.read) {
      await markAsRead(notification.id);
    }
    // Navigate to event
    router.push(`/events?event=${notification.event_id}`);
    onClose?.();
  };

  const handleMarkAllRead = async () => {
    await markAllAsRead();
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation(); // Prevent triggering notification click
    await deleteNotification(id);
  };

  if (isLoading) {
    return (
      <div className="w-[400px] max-w-[calc(100vw-2rem)] bg-background border rounded-lg shadow-lg">
        <div className="flex items-center justify-center p-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      </div>
    );
  }

  return (
    <div className="w-[400px] max-w-[calc(100vw-2rem)] bg-background border rounded-lg shadow-lg">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <h3 className="font-semibold text-sm">Notifications</h3>
        {unreadCount > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="text-xs text-primary hover:text-primary"
            onClick={handleMarkAllRead}
          >
            <Check className="h-3 w-3 mr-1" />
            Mark all as read
          </Button>
        )}
      </div>

      {/* Notification List */}
      <ScrollArea className="max-h-[500px]">
        {notifications.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
            <p className="text-sm text-muted-foreground">No notifications yet</p>
            <p className="text-xs text-muted-foreground mt-1">
              You&apos;ll see alerts here when rules trigger
            </p>
          </div>
        ) : (
          <div className="divide-y">
            {notifications.map((notification) => (
              <NotificationItem
                key={notification.id}
                notification={notification}
                onClick={() => handleNotificationClick(notification)}
                onDelete={(e) => handleDelete(e, notification.id)}
              />
            ))}
          </div>
        )}
      </ScrollArea>

      {/* Footer */}
      {notifications.length > 0 && (
        <div className="px-4 py-2 border-t text-center">
          <Button
            variant="link"
            size="sm"
            className="text-xs"
            onClick={() => {
              router.push('/events?filter=alerts');
              onClose?.();
            }}
          >
            View all events
          </Button>
        </div>
      )}
    </div>
  );
}

interface NotificationItemProps {
  notification: INotification;
  onClick: () => void;
  onDelete: (e: React.MouseEvent) => void;
}

function NotificationItem({ notification, onClick, onDelete }: NotificationItemProps) {
  const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

  // Format relative timestamp
  const timeAgo = formatDistanceToNow(new Date(notification.created_at), {
    addSuffix: true,
  });

  // Build thumbnail URL
  const thumbnailUrl = notification.thumbnail_url
    ? `${API_BASE_URL}${notification.thumbnail_url}`
    : null;

  return (
    <div
      className={cn(
        'flex gap-3 p-3 cursor-pointer transition-colors hover:bg-muted/50 group',
        !notification.read && 'bg-primary/5'
      )}
      onClick={onClick}
    >
      {/* Unread indicator */}
      <div className="flex-shrink-0 mt-1">
        {!notification.read ? (
          <div className="h-2 w-2 rounded-full bg-primary" />
        ) : (
          <div className="h-2 w-2" /> // Spacer for alignment
        )}
      </div>

      {/* Thumbnail */}
      <div className="flex-shrink-0">
        {thumbnailUrl ? (
          <img
            src={thumbnailUrl}
            alt=""
            className="h-16 w-16 rounded object-cover bg-muted"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = 'none';
            }}
          />
        ) : (
          <div className="h-16 w-16 rounded bg-muted flex items-center justify-center">
            <span className="text-xs text-muted-foreground">No image</span>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <p
          className={cn(
            'text-sm truncate',
            !notification.read && 'font-semibold'
          )}
        >
          {notification.rule_name}
        </p>
        {notification.event_description && (
          <p className="text-xs text-muted-foreground line-clamp-2 mt-0.5">
            {notification.event_description.slice(0, 100)}
          </p>
        )}
        <p className="text-xs text-muted-foreground mt-1">
          {timeAgo}
        </p>
      </div>

      {/* Delete button (shows on hover) */}
      <div className="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground hover:text-destructive"
          onClick={onDelete}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
