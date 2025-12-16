/**
 * Application header with navigation (updated for Story 6.3)
 */

'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Video, Calendar, Bell, Settings, Menu, Home, User, Circle, LogOut, KeyRound, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import { useState } from 'react';
import { NotificationBell } from '@/components/notifications';
import { useAuth } from '@/contexts/AuthContext';
import { useSettings } from '@/contexts/SettingsContext';
import { toast } from 'sonner';

const navigation = [
  { name: 'Dashboard', href: '/', icon: Home, available: true },
  { name: 'Events', href: '/events', icon: Calendar, available: true },
  { name: 'Cameras', href: '/cameras', icon: Video, available: true },
  { name: 'Entities', href: '/entities', icon: Users, available: true },
  { name: 'Rules', href: '/rules', icon: Bell, available: true },
  { name: 'Settings', href: '/settings', icon: Settings, available: true },
];

/**
 * Header component with navigation menu
 */
export function Header() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout, isAuthenticated } = useAuth();
  const { settings } = useSettings(); // BUG-003: Get system name from settings
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const handleLogout = async () => {
    try {
      await logout();
      toast.success('Logged out successfully');
      router.push('/login');
    } catch (error) {
      console.error('Logout error:', error);
      // Still redirect even if logout API fails
      router.push('/login');
    }
  };

  return (
    // IMP-003: Hide header on desktop (lg+) since sidebar provides navigation
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 lg:hidden">
      <div className="container mx-auto px-4">
        <div className="flex h-16 items-center justify-between">
          {/* Logo - BUG-003: Use dynamic system name */}
          <Link href="/" className="flex items-center gap-2" aria-label={`${settings.systemName} - Home`}>
            <div className="p-2 bg-primary/10 rounded-lg">
              <Video className="h-6 w-6 text-primary" aria-hidden="true" />
            </div>
            <span className="font-bold text-xl hidden sm:inline-block">
              {settings.systemName}
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
                    'flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
                    isActive
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                    !item.available && 'opacity-50 cursor-not-allowed'
                  )}
                  onClick={(e) => !item.available && e.preventDefault()}
                  aria-label={item.name}
                  aria-current={isActive ? 'page' : undefined}
                  aria-disabled={!item.available}
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
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
                  <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted/50" role="status" aria-label="System status: Healthy">
                    <Circle className="h-2 w-2 fill-green-500 text-green-500" aria-hidden="true" />
                    <span className="text-xs font-medium hidden sm:inline">Healthy</span>
                  </div>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="text-xs">System Status: Healthy</p>
                  <p className="text-xs text-muted-foreground">All services operational</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            {/* Notification Bell (Story 5.4) */}
            <NotificationBell />

            {/* User Menu (Story 6.3) */}
            {isAuthenticated && user && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="hidden md:flex" aria-label={`User menu for ${user.username}`} aria-haspopup="menu">
                    <User className="h-5 w-5" aria-hidden="true" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
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

            {/* Mobile Menu Button */}
            <Button
              variant="ghost"
              size="sm"
              className="md:hidden"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              aria-label={mobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}
              aria-expanded={mobileMenuOpen}
              aria-controls="mobile-navigation"
            >
              <Menu className="h-5 w-5" aria-hidden="true" />
            </Button>
          </div>
        </div>

        {/* Mobile Navigation */}
        {mobileMenuOpen && (
          <nav id="mobile-navigation" className="md:hidden pb-4 space-y-1" aria-label="Mobile navigation">
            {navigation.map((item) => {
              const isActive = pathname?.startsWith(item.href);
              const Icon = item.icon;

              return (
                <Link
                  key={item.name}
                  href={item.available ? item.href : '#'}
                  className={cn(
                    'flex items-center gap-3 px-4 py-3 rounded-md text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
                    isActive
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                    !item.available && 'opacity-50 cursor-not-allowed'
                  )}
                  onClick={(e) => {
                    if (!item.available) e.preventDefault();
                    setMobileMenuOpen(false);
                  }}
                  aria-label={item.name}
                  aria-current={isActive ? 'page' : undefined}
                  aria-disabled={!item.available}
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
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
