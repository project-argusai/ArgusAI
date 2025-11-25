/**
 * App Shell - Protected layout wrapper (Story 6.3)
 *
 * Handles authentication and conditionally renders:
 * - Login page: No header/sidebar, full screen
 * - Protected pages: Full layout with auth check
 */

'use client';

import { usePathname } from 'next/navigation';
import { Header } from '@/components/layout/Header';
import { Sidebar } from '@/components/layout/Sidebar';
import { MobileNav } from '@/components/layout/MobileNav';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';

interface AppShellProps {
  children: React.ReactNode;
}

// Public routes that don't require authentication
const PUBLIC_ROUTES = ['/login'];

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const isPublicRoute = PUBLIC_ROUTES.some(route => pathname?.startsWith(route));

  // Public routes: render without layout
  if (isPublicRoute) {
    return <>{children}</>;
  }

  // Protected routes: wrap with auth check and full layout
  return (
    <ProtectedRoute>
      <Header />
      <Sidebar />
      <main className="min-h-screen bg-background pt-16 pb-16 lg:pb-0 lg:pl-60 transition-all duration-300">
        <div className="container mx-auto">
          {children}
        </div>
      </main>
      <MobileNav />
    </ProtectedRoute>
  );
}
