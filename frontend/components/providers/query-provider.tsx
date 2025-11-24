/**
 * TanStack Query provider configuration
 * Wraps the app to enable data fetching, caching, and state management
 */

'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode, useState } from 'react';

export function QueryProvider({ children }: { children: ReactNode }) {
  // Create a client instance (initialized once per user session)
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Default query options
            staleTime: 60 * 1000, // Data fresh for 1 minute
            gcTime: 5 * 60 * 1000, // Garbage collect after 5 minutes (previously cacheTime)
            refetchOnWindowFocus: false, // Don't refetch on window focus by default
            refetchOnMount: true, // Refetch when component mounts
            refetchOnReconnect: true, // Refetch when network reconnects
            retry: 1, // Retry failed requests once
          },
          mutations: {
            // Default mutation options
            retry: 0, // Don't retry mutations
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}
