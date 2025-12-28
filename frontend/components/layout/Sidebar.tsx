/**
 * Desktop sidebar navigation with collapse/expand functionality
 * Visible only on screens >= 1024px (lg breakpoint)
 * Status, notifications, and user menu are in DesktopToolbar (top-right corner)
 */

'use client';

import Link from 'next/link';
import Image from 'next/image';
import { usePathname } from 'next/navigation';
import { Home, Calendar, Video, Bell, Settings, ChevronLeft, ChevronRight, Users, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useState } from 'react';
import { useSettings } from '@/contexts/SettingsContext';

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
 * Status, notifications, and user menu are now in DesktopToolbar
 */
export function Sidebar() {
  const pathname = usePathname();
  const { settings } = useSettings();

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
        {/* P13-4.2: Use ArgusAI logo image */}
        <div className={cn(
          "flex items-center gap-2 p-4 border-b",
          isCollapsed ? "justify-center" : ""
        )}>
          <Image
            src="/icons/icon-96.png"
            alt=""
            width={28}
            height={28}
            className="rounded-lg flex-shrink-0"
            aria-hidden="true"
            priority
          />
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
