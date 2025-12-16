/**
 * Mobile bottom navigation bar
 * Visible only on screens < 1024px (below lg breakpoint)
 */

'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Home, Calendar, Video, Bell, Settings } from 'lucide-react';
import { cn } from '@/lib/utils';

const navigation = [
  { name: 'Home', href: '/', icon: Home },
  { name: 'Events', href: '/events', icon: Calendar },
  { name: 'Cameras', href: '/cameras', icon: Video },
  { name: 'Rules', href: '/rules', icon: Bell },
  { name: 'Settings', href: '/settings', icon: Settings },
];

/**
 * Mobile navigation component
 * Shows as fixed bottom tab bar on mobile devices
 */
export function MobileNav() {
  const pathname = usePathname();

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 lg:hidden">
      <div className="flex justify-around items-center h-16 px-2">
        {navigation.map((item) => {
          const isActive = pathname === item.href || (item.href !== '/' && pathname?.startsWith(item.href));
          const Icon = item.icon;

          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                'flex flex-col items-center justify-center gap-1 px-3 py-2 rounded-lg min-w-[64px] transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2',
                isActive
                  ? 'text-blue-600'
                  : 'text-muted-foreground hover:text-foreground'
              )}
              aria-label={item.name}
              aria-current={isActive ? 'page' : undefined}
            >
              <Icon className={cn('h-5 w-5', isActive && 'fill-blue-600/20')} aria-hidden="true" />
              <span className="text-xs font-medium">{item.name}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
