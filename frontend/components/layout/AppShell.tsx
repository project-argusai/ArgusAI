/**
 * App Shell - Protected layout wrapper (Story 6.3)
 * FF-005: Mobile navigation uses top bar only (hamburger menu in Header)
 *
 * Handles authentication and conditionally renders:
 * - Login page: No header/sidebar, full screen
 * - Protected pages: Full layout with auth check
 */

'use client';

import { usePathname } from 'next/navigation';
import { Header } from '@/components/layout/Header';
import { Sidebar } from '@/components/layout/Sidebar';
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
  // FF-005: Removed MobileNav (bottom bar) - mobile uses hamburger menu in Header instead
  return (
    <ProtectedRoute>
      <Header />
      <Sidebar />
      <main className="min-h-screen bg-background pt-16 lg:pl-60 transition-all duration-300">
        <div className="container mx-auto">
          {children}
        </div>
      </main>
    </ProtectedRoute>
  );
}
