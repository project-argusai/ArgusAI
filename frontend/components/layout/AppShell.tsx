/**
 * App Shell - Protected layout wrapper (Story 6.3, P16-1.5)
 * FF-005: Mobile navigation uses top bar only (hamburger menu in Header)
 *
 * Handles authentication and conditionally renders:
 * - Login page: No header/sidebar, full screen
 * - Change password page: Protected but no layout (P16-1.5)
 * - Protected pages: Full layout with auth check
 *
 * Updated for Story P4-1.5: Added PWA install prompt and update banner
 */

'use client';

import { usePathname } from 'next/navigation';
import { Header } from '@/components/layout/Header';
import { Sidebar } from '@/components/layout/Sidebar';
import { DesktopToolbar } from '@/components/layout/DesktopToolbar';
import { SkipToContent } from '@/components/layout/SkipToContent';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { InstallPrompt } from '@/components/pwa/InstallPrompt';
import { ServiceWorkerUpdateBanner } from '@/components/pwa/ServiceWorkerUpdateBanner';

interface AppShellProps {
  children: React.ReactNode;
}

// Public routes that don't require authentication
const PUBLIC_ROUTES = ['/login'];

// Routes that require auth but no layout (P16-1.5)
const AUTH_NO_LAYOUT_ROUTES = ['/change-password'];

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const isPublicRoute = PUBLIC_ROUTES.some(route => pathname?.startsWith(route));
  const isAuthNoLayoutRoute = AUTH_NO_LAYOUT_ROUTES.some(route => pathname?.startsWith(route));

  // Public routes: render without layout
  if (isPublicRoute) {
    return <>{children}</>;
  }

  // Story P16-1.5: Auth required but no layout (change-password page)
  if (isAuthNoLayoutRoute) {
    return <ProtectedRoute>{children}</ProtectedRoute>;
  }

  // Protected routes: wrap with auth check and full layout
  // FF-005: Removed MobileNav (bottom bar) - mobile uses hamburger menu in Header instead
  // IMP-003: Header hidden on desktop (lg+), only visible on mobile/tablet
  // P6-2.1: SkipToContent renders first for keyboard accessibility (WCAG 2.4.1)
  return (
    <ProtectedRoute>
      <SkipToContent />
      <Header />
      <Sidebar />
      <DesktopToolbar />
      {/* IMP-003: pt-16 for header space on mobile, pt-0 on desktop (header hidden) */}
      {/* P6-2.1: id="main-content" and tabIndex={-1} for skip link target */}
      <main
        id="main-content"
        tabIndex={-1}
        className="min-h-screen bg-background pt-16 lg:pt-0 lg:pl-60 transition-all duration-300 outline-none"
      >
        <div className="container mx-auto">
          {children}
        </div>
      </main>
      {/* PWA install prompt - shows banner for eligible users */}
      <InstallPrompt variant="banner" />
      {/* Service worker update banner - shows when new version available */}
      <ServiceWorkerUpdateBanner />
    </ProtectedRoute>
  );
}
