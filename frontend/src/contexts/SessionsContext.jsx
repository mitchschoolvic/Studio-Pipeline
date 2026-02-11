import { createContext, useContext, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useWebSocketMessages } from '../hooks/useWebSocketMessages';

/**
 * SessionsContext - Adapter layer for React Query
 *
 * Replaces the Zustand store with TanStack Query for state management.
 * Maintains the same API for existing components.
 */

const SessionsContext = createContext(null);

export function SessionsProvider({ children }) {
  // Use centralized WebSocket message handler (which will now update Query Cache)
  useWebSocketMessages();
  const queryClient = useQueryClient();

  // Fetch sessions
  const { data: sessions = [], refetch: fetchSessions, isLoading } = useQuery({
    queryKey: ['sessions'],
    queryFn: async () => {
      const res = await fetch('/api/sessions/?limit=1000');
      if (!res.ok) throw new Error('Failed to fetch sessions');
      return res.json();
    },
    select: (data) => {
      // Deduplicate sessions by ID
      const seen = new Set();
      return data.filter(session => {
        if (seen.has(session.id)) return false;
        seen.add(session.id);
        return true;
      });
    }
  });

  // Ensure files for a session
  const ensureSessionFiles = useCallback(async (sessionId, options = {}) => {
    const { limit = 200, offset = 0 } = options;

    // We use fetchQuery to get data if not stale, or trigger a fetch
    return queryClient.fetchQuery({
      queryKey: ['session-files', sessionId],
      queryFn: async () => {
        const res = await fetch(`/api/sessions/${sessionId}/files/?limit=${limit}&offset=${offset}&include_jobs=true`);
        if (!res.ok) throw new Error('Failed to fetch files');
        return res.json();
      },
      staleTime: 1000 * 60 * 5 // 5 minutes
    });
  }, [queryClient]);

  // Get files from cache (synchronous)
  const getFiles = useCallback((sessionId) => {
    return queryClient.getQueryData(['session-files', sessionId]) || [];
  }, [queryClient]);

  const value = {
    sessions,
    fetchSessions,
    ensureSessionFiles,
    getFiles,
    isLoading
  };

  return <SessionsContext.Provider value={value}>{children}</SessionsContext.Provider>;
}

export function useSessions() {
  const ctx = useContext(SessionsContext);
  if (!ctx) throw new Error('useSessions must be used within SessionsProvider');
  return ctx;
}
