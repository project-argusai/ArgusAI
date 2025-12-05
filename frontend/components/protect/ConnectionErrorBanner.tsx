/**
 * Connection Error Banner Component
 * Story P2-6.3: Phase 2 Error Handling
 *
 * Displays context-aware error banners for controller connection issues:
 * - Yellow: Auto-retry in progress (Unable to connect)
 * - Red: Authentication failed (requires credential check)
 * - Red: Controller unreachable (with manual retry button)
 *
 * AC1: Controller connection errors show appropriate banners
 * AC2: "Unable to connect" shows yellow banner with auto-retry in progress
 * AC3: "Authentication failed" shows red banner prompting credential check
 * AC4: "Controller unreachable" shows red banner with manual retry button
 */

'use client';

import { AlertCircle, AlertTriangle, Loader2, RefreshCw, KeyRound, WifiOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export type ConnectionErrorType =
  | 'connecting'       // Yellow: Auto-retry in progress
  | 'auth_failed'      // Red: Authentication failed
  | 'unreachable'      // Red: Controller unreachable
  | 'ssl_error'        // Red: SSL certificate error
  | 'timeout'          // Yellow: Connection timeout (auto-retry)
  | 'unknown';         // Red: Unknown error

interface ConnectionErrorBannerProps {
  errorType: ConnectionErrorType;
  errorMessage?: string;
  retryCount?: number;
  maxRetries?: number;
  isRetrying?: boolean;
  onRetry?: () => void;
  onEditCredentials?: () => void;
  className?: string;
}

/**
 * Configuration for each error type
 */
const errorConfig: Record<ConnectionErrorType, {
  variant: 'warning' | 'error';
  icon: typeof AlertCircle;
  title: string;
  showRetrySpinner: boolean;
  showRetryButton: boolean;
  showEditCredentials: boolean;
}> = {
  connecting: {
    variant: 'warning',
    icon: Loader2,
    title: 'Connecting to controller...',
    showRetrySpinner: true,
    showRetryButton: false,
    showEditCredentials: false,
  },
  auth_failed: {
    variant: 'error',
    icon: KeyRound,
    title: 'Authentication Failed',
    showRetrySpinner: false,
    showRetryButton: false,
    showEditCredentials: true,
  },
  unreachable: {
    variant: 'error',
    icon: WifiOff,
    title: 'Controller Unreachable',
    showRetrySpinner: false,
    showRetryButton: true,
    showEditCredentials: false,
  },
  ssl_error: {
    variant: 'error',
    icon: AlertCircle,
    title: 'SSL Certificate Error',
    showRetrySpinner: false,
    showRetryButton: false,
    showEditCredentials: true,
  },
  timeout: {
    variant: 'warning',
    icon: AlertTriangle,
    title: 'Connection Timeout',
    showRetrySpinner: true,
    showRetryButton: true,
    showEditCredentials: false,
  },
  unknown: {
    variant: 'error',
    icon: AlertCircle,
    title: 'Connection Error',
    showRetrySpinner: false,
    showRetryButton: true,
    showEditCredentials: false,
  },
};

/**
 * Connection Error Banner
 * Displays a color-coded banner with appropriate actions based on error type
 */
export function ConnectionErrorBanner({
  errorType,
  errorMessage,
  retryCount = 0,
  maxRetries = 6,
  isRetrying = false,
  onRetry,
  onEditCredentials,
  className,
}: ConnectionErrorBannerProps) {
  const config = errorConfig[errorType];
  const Icon = config.icon;
  const isWarning = config.variant === 'warning';

  // Show retry progress if auto-retrying
  const retryProgress = retryCount > 0 && retryCount < maxRetries
    ? `Retry ${retryCount}/${maxRetries}`
    : undefined;

  return (
    <div
      className={cn(
        'rounded-lg border p-4',
        isWarning
          ? 'bg-yellow-50 border-yellow-200 text-yellow-800 dark:bg-yellow-950 dark:border-yellow-800 dark:text-yellow-200'
          : 'bg-red-50 border-red-200 text-red-800 dark:bg-red-950 dark:border-red-800 dark:text-red-200',
        className
      )}
      role="alert"
      aria-live="polite"
    >
      <div className="flex items-start gap-3">
        {/* Icon */}
        <div className="flex-shrink-0 mt-0.5">
          {config.showRetrySpinner && isRetrying ? (
            <Loader2 className={cn('h-5 w-5 animate-spin', isWarning ? 'text-yellow-600' : 'text-red-600')} />
          ) : (
            <Icon className={cn('h-5 w-5', isWarning ? 'text-yellow-600' : 'text-red-600')} />
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <h4 className="font-medium text-sm">{config.title}</h4>

          {errorMessage && (
            <p className="text-sm mt-1 opacity-90">{errorMessage}</p>
          )}

          {retryProgress && (
            <p className="text-xs mt-1 opacity-75">{retryProgress}</p>
          )}

          {/* Specific guidance based on error type */}
          {errorType === 'auth_failed' && (
            <p className="text-sm mt-2 opacity-90">
              Please check your username and password.
            </p>
          )}

          {errorType === 'ssl_error' && (
            <p className="text-sm mt-2 opacity-90">
              Try disabling SSL verification if using a self-signed certificate.
            </p>
          )}

          {errorType === 'unreachable' && (
            <p className="text-sm mt-2 opacity-90">
              Check that the controller is powered on and accessible on your network.
            </p>
          )}
        </div>

        {/* Actions */}
        <div className="flex-shrink-0 flex items-center gap-2">
          {config.showRetryButton && onRetry && (
            <Button
              variant="outline"
              size="sm"
              onClick={onRetry}
              disabled={isRetrying}
              className={cn(
                'border',
                isWarning
                  ? 'border-yellow-300 hover:bg-yellow-100 text-yellow-700'
                  : 'border-red-300 hover:bg-red-100 text-red-700'
              )}
            >
              {isRetrying ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  <RefreshCw className="h-4 w-4 mr-1" />
                  Retry
                </>
              )}
            </Button>
          )}

          {config.showEditCredentials && onEditCredentials && (
            <Button
              variant="outline"
              size="sm"
              onClick={onEditCredentials}
              className={cn(
                'border',
                isWarning
                  ? 'border-yellow-300 hover:bg-yellow-100 text-yellow-700'
                  : 'border-red-300 hover:bg-red-100 text-red-700'
              )}
            >
              <KeyRound className="h-4 w-4 mr-1" />
              Edit Credentials
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Helper function to determine error type from error message or HTTP status
 */
export function getConnectionErrorType(
  statusCode?: number,
  errorMessage?: string
): ConnectionErrorType {
  // Check status code first
  if (statusCode) {
    switch (statusCode) {
      case 401:
        return 'auth_failed';
      case 502:
        return 'ssl_error';
      case 503:
        return 'unreachable';
      case 504:
        return 'timeout';
    }
  }

  // Check error message patterns
  if (errorMessage) {
    const lower = errorMessage.toLowerCase();
    if (lower.includes('authentication') || lower.includes('unauthorized') || lower.includes('password') || lower.includes('credential')) {
      return 'auth_failed';
    }
    if (lower.includes('ssl') || lower.includes('certificate')) {
      return 'ssl_error';
    }
    if (lower.includes('unreachable') || lower.includes('network') || lower.includes('connect')) {
      return 'unreachable';
    }
    if (lower.includes('timeout') || lower.includes('timed out')) {
      return 'timeout';
    }
  }

  return 'unknown';
}
