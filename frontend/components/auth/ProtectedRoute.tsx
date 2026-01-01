/**
 * Protected Route wrapper component (Story 6.3, AC: #9, P16-1.5)
 *
 * Wraps pages that require authentication.
 * Redirects to /login if not authenticated.
 * Redirects to /change-password if must_change_password is true (P16-1.5).
 * Preserves return URL for post-login redirect.
 */

'use client';

import { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

interface ProtectedRouteProps {
  children: React.ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      // Redirect to login with return URL
      const returnUrl = encodeURIComponent(pathname);
      router.push(`/login?returnUrl=${returnUrl}`);
    }
  }, [isAuthenticated, isLoading, pathname, router]);

  // Story P16-1.5: Force password change redirect
  // If user must change password, redirect to change-password page
  // Exception: Don't redirect if already on change-password page
  useEffect(() => {
    if (!isLoading && isAuthenticated && user?.must_change_password) {
      if (pathname !== '/change-password') {
        router.push('/change-password');
      }
    }
  }, [isAuthenticated, isLoading, user, pathname, router]);

  // Show loading spinner while checking auth
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
          <p className="text-gray-500 dark:text-gray-400">Loading...</p>
        </div>
      </div>
    );
  }

  // Don't render children if not authenticated
  if (!isAuthenticated) {
    return null;
  }

  // Story P16-1.5: Don't render protected content if password change required
  // (redirect will happen via useEffect above)
  if (user?.must_change_password && pathname !== '/change-password') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
          <p className="text-gray-500 dark:text-gray-400">Redirecting to password change...</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
