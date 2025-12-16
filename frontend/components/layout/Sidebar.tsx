/**
 * Desktop sidebar navigation with collapse/expand functionality
 * Visible only on screens >= 1024px (lg breakpoint)
 * IMP-003: Now includes header elements (notifications, user menu) since header is hidden on desktop
 */

'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Home, Calendar, Video, Bell, Settings, ChevronLeft, ChevronRight, User, LogOut, KeyRound, Circle, Users, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { useState } from 'react';
import { NotificationBell } from '@/components/notifications';
import { useAuth } from '@/contexts/AuthContext';
import { useSettings } from '@/contexts/SettingsContext';
import { toast } from 'sonner';

const navigation = [
  { name: 'Dashboard', href: '/', icon: Home },
  { name: 'Events', href: '/events', icon: Calendar },
  { name: 'Cameras', href: '/cameras', icon: Video },
  { name: 'Entities', href: '/entities', icon: Users },
  { name: 'Summaries', href: '/summaries', icon: Sparkles },
  { name: 'Rules', href: '/rules', icon: Bell },
  { name: 'Settings', href: '/settings', icon: Settings },
];

/**
 * Sidebar component for desktop navigation
 * Persists collapsed state in localStorage
 * IMP-003: Now starts from top (no header on desktop) and includes notifications/user menu
 */
export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout, isAuthenticated } = useAuth();
  const { settings } = useSettings(); // BUG-003: Get system name from settings

  // Load collapsed state from localStorage on mount - only once
  const [isCollapsed, setIsCollapsed] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('sidebar-collapsed');
      return saved === 'true';
    }
    return false;
  });

  // Save collapsed state to localStorage
  const toggleCollapse = () => {
    const newState = !isCollapsed;
    setIsCollapsed(newState);
    localStorage.setItem('sidebar-collapsed', String(newState));
  };

  const handleLogout = async () => {
    try {
      await logout();
      toast.success('Logged out successfully');
      router.push('/login');
    } catch (error) {
      console.error('Logout error:', error);
      router.push('/login');
    }
  };

  return (
    <aside
      className={cn(
        // IMP-003: Changed top-16 to top-0 since header is hidden on desktop
        'fixed left-0 top-0 bottom-0 z-40 border-r bg-background transition-all duration-300 hidden lg:block',
        isCollapsed ? 'w-16' : 'w-60'
      )}
    >
      <div className="flex flex-col h-full">
        {/* IMP-003: App branding header in sidebar */}
        {/* BUG-003: Use dynamic system name from settings */}
        <div className={cn(
          "flex items-center gap-2 p-4 border-b",
          isCollapsed ? "justify-center" : ""
        )}>
          <div className="p-1.5 bg-primary/10 rounded-lg flex-shrink-0">
            <Video className="h-5 w-5 text-primary" aria-hidden="true" />
          </div>
          {!isCollapsed && (
            <span className="font-bold text-lg truncate">{settings.systemName}</span>
          )}
        </div>

        {/* Navigation Links */}
        <nav className="flex-1 p-3 space-y-1">
          {navigation.map((item) => {
            const isActive = pathname === item.href || (item.href !== '/' && pathname?.startsWith(item.href));
            const Icon = item.icon;

            return (
              <Link
                key={item.name}
                href={item.href}
                className={cn(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2',
                  isActive
                    ? 'bg-blue-600 text-white'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                  isCollapsed && 'justify-center'
                )}
                title={isCollapsed ? item.name : undefined}
                aria-label={item.name}
                aria-current={isActive ? 'page' : undefined}
              >
                <Icon className={cn('h-5 w-5', isCollapsed ? '' : 'flex-shrink-0')} aria-hidden="true" />
                {!isCollapsed && <span>{item.name}</span>}
              </Link>
            );
          })}
        </nav>

        {/* IMP-003: Status, Notifications, and User Menu (moved from header) */}
        <div className={cn(
          "p-3 border-t space-y-2",
          isCollapsed ? "flex flex-col items-center" : ""
        )}>
          {/* System Status */}
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className={cn(
                  "flex items-center gap-1.5 px-2 py-1.5 rounded-md bg-muted/50",
                  isCollapsed ? "justify-center" : ""
                )}>
                  <Circle className="h-2 w-2 fill-green-500 text-green-500" aria-hidden="true" />
                  {!isCollapsed && <span className="text-xs font-medium">Healthy</span>}
                </div>
              </TooltipTrigger>
              <TooltipContent side="right">
                <p className="text-xs">System Status: Healthy</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>

          {/* Notifications */}
          <div className={cn(isCollapsed ? "flex justify-center" : "")}>
            <NotificationBell />
          </div>

          {/* User Menu */}
          {isAuthenticated && user && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className={cn(
                    "w-full",
                    isCollapsed ? "px-0 justify-center" : "justify-start"
                  )}
                  aria-label={`User menu for ${user.username}`}
                  aria-haspopup="menu"
                >
                  <User className="h-4 w-4" aria-hidden="true" />
                  {!isCollapsed && <span className="ml-2 truncate">{user.username}</span>}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" side="right" className="w-56">
                <DropdownMenuLabel>
                  <div className="flex flex-col space-y-1">
                    <p className="text-sm font-medium">{user.username}</p>
                    <p className="text-xs text-muted-foreground">Logged in</p>
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem asChild>
                  <Link href="/settings" className="flex items-center gap-2 cursor-pointer">
                    <Settings className="h-4 w-4" aria-hidden="true" />
                    Settings
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link href="/settings?tab=security" className="flex items-center gap-2 cursor-pointer">
                    <KeyRound className="h-4 w-4" aria-hidden="true" />
                    Change Password
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={handleLogout}
                  className="flex items-center gap-2 cursor-pointer text-red-600 dark:text-red-400"
                >
                  <LogOut className="h-4 w-4" aria-hidden="true" />
                  Logout
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>

        {/* Collapse/Expand Button */}
        <div className="p-3 border-t">
          <Button
            variant="ghost"
            size="sm"
            onClick={toggleCollapse}
            className={cn(
              'w-full',
              isCollapsed ? 'px-0 justify-center' : 'justify-start'
            )}
            aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-expanded={!isCollapsed}
          >
            {isCollapsed ? (
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            ) : (
              <>
                <ChevronLeft className="h-4 w-4 mr-2" aria-hidden="true" />
                <span className="text-xs">Collapse</span>
              </>
            )}
          </Button>
        </div>
      </div>
    </aside>
  );
}
