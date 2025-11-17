/**
 * Application header with navigation
 */

'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Video, Calendar, Bell, Settings, Menu, Home, User, Circle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { useState } from 'react';

const navigation = [
  { name: 'Dashboard', href: '/', icon: Home, available: true },
  { name: 'Events', href: '/events', icon: Calendar, available: true },
  { name: 'Cameras', href: '/cameras', icon: Video, available: true },
  { name: 'Rules', href: '/rules', icon: Bell, available: true },
  { name: 'Settings', href: '/settings', icon: Settings, available: true },
];

/**
 * Header component with navigation menu
 */
export function Header() {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto px-4">
        <div className="flex h-16 items-center justify-between">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2">
            <div className="p-2 bg-primary/10 rounded-lg">
              <Video className="h-6 w-6 text-primary" />
            </div>
            <span className="font-bold text-xl hidden sm:inline-block">
              Live Object AI
            </span>
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center gap-1">
            {navigation.map((item) => {
              const isActive = pathname?.startsWith(item.href);
              const Icon = item.icon;

              return (
                <Link
                  key={item.name}
                  href={item.available ? item.href : '#'}
                  className={cn(
                    'flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                    !item.available && 'opacity-50 cursor-not-allowed'
                  )}
                  onClick={(e) => !item.available && e.preventDefault()}
                >
                  <Icon className="h-4 w-4" />
                  {item.name}
                  {!item.available && (
                    <span className="text-xs">(Soon)</span>
                  )}
                </Link>
              );
            })}
          </nav>

          {/* Right Side Actions */}
          <div className="flex items-center gap-2">
            {/* System Status Indicator */}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted/50">
                    <Circle className="h-2 w-2 fill-green-500 text-green-500" />
                    <span className="text-xs font-medium hidden sm:inline">Healthy</span>
                  </div>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="text-xs">System Status: Healthy</p>
                  <p className="text-xs text-muted-foreground">All services operational</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            {/* Notification Bell */}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon" className="relative">
                    <Bell className="h-5 w-5" />
                    <Badge
                      variant="destructive"
                      className="absolute -top-1 -right-1 h-5 w-5 flex items-center justify-center p-0 text-xs"
                    >
                      0
                    </Badge>
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="text-xs">No new notifications</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            {/* User Menu (Phase 1.5 Placeholder) */}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon" className="hidden md:flex">
                    <User className="h-5 w-5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="text-xs">User menu coming in Phase 1.5</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            {/* Mobile Menu Button */}
            <Button
              variant="ghost"
              size="sm"
              className="md:hidden"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              <Menu className="h-5 w-5" />
            </Button>
          </div>
        </div>

        {/* Mobile Navigation */}
        {mobileMenuOpen && (
          <nav className="md:hidden pb-4 space-y-1">
            {navigation.map((item) => {
              const isActive = pathname?.startsWith(item.href);
              const Icon = item.icon;

              return (
                <Link
                  key={item.name}
                  href={item.available ? item.href : '#'}
                  className={cn(
                    'flex items-center gap-3 px-4 py-3 rounded-md text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                    !item.available && 'opacity-50 cursor-not-allowed'
                  )}
                  onClick={(e) => {
                    if (!item.available) e.preventDefault();
                    setMobileMenuOpen(false);
                  }}
                >
                  <Icon className="h-4 w-4" />
                  {item.name}
                  {!item.available && (
                    <span className="text-xs ml-auto">(Soon)</span>
                  )}
                </Link>
              );
            })}
          </nav>
        )}
      </div>
    </header>
  );
}
