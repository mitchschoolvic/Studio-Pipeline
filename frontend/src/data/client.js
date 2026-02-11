import { QueryClient } from '@tanstack/react-query';

/**
 * Global React Query client with optimized cache settings
 * - staleTime: 60s - Data is fresh for 1 minute
 * - gcTime: 5 minutes - Unused data kept in cache for 5 minutes
 * - refetchOnWindowFocus: false - Don't refetch when user returns to tab
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000, // 60 seconds
      gcTime: 300_000, // 5 minutes
      refetchOnWindowFocus: false,
      refetchOnReconnect: 'always',
      retry: 1,
    },
    mutations: {
      retry: 1,
    },
  },
});
