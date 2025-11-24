/**
 * Notification bell icon with dropdown (Story 5.4)
 *
 * Features:
 * - Bell icon with unread count badge
 * - Click to toggle dropdown
 * - Real-time count updates from WebSocket
 */

'use client';

import { useState, useRef, useEffect } from 'react';
import { Bell } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useNotifications } from '@/contexts/NotificationContext';
import { NotificationDropdown } from './NotificationDropdown';
import { cn } from '@/lib/utils';

export function NotificationBell() {
  const [isOpen, setIsOpen] = useState(false);
  const { unreadCount, connectionStatus } = useNotifications();
  const dropdownRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        buttonRef.current &&
        !buttonRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // Close dropdown on Escape key
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen]);

  const tooltipText = unreadCount > 0
    ? `${unreadCount} unread notification${unreadCount !== 1 ? 's' : ''}`
    : 'No new notifications';

  return (
    <div className="relative">
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              ref={buttonRef}
              variant="ghost"
              size="icon"
              className="relative"
              onClick={() => setIsOpen(!isOpen)}
              aria-label={tooltipText}
              aria-expanded={isOpen}
              aria-haspopup="true"
            >
              <Bell className={cn(
                'h-5 w-5',
                unreadCount > 0 && 'text-primary'
              )} />
              {unreadCount > 0 && (
                <Badge
                  variant="destructive"
                  className="absolute -top-1 -right-1 h-5 min-w-5 flex items-center justify-center p-0 text-xs"
                >
                  {unreadCount > 99 ? '99+' : unreadCount}
                </Badge>
              )}
              {/* Connection status indicator */}
              {connectionStatus !== 'connected' && (
                <span
                  className={cn(
                    'absolute bottom-0 right-0 h-2 w-2 rounded-full',
                    connectionStatus === 'connecting' || connectionStatus === 'reconnecting'
                      ? 'bg-yellow-500 animate-pulse'
                      : 'bg-gray-400'
                  )}
                  title={`WebSocket: ${connectionStatus}`}
                />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p className="text-xs">{tooltipText}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      {/* Dropdown */}
      {isOpen && (
        <div
          ref={dropdownRef}
          className="absolute right-0 top-full mt-2 z-50"
        >
          <NotificationDropdown onClose={() => setIsOpen(false)} />
        </div>
      )}
    </div>
  );
}
