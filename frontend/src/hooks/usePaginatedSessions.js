import { useState, useCallback, useRef } from 'react';

/**
 * usePaginatedSessions
 * Handles paginated session summaries and lazy file loading.
 * Scales to thousands of sessions/files by avoiding large upfront payloads.
 */
export function usePaginatedSessions(initialLimit = 50) {
  const [sessions, setSessions] = useState([]); // [{id,name,..., files:[]?}]
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [hasMore, setHasMore] = useState(true);
  const offsetRef = useRef(0);
  const limitRef = useRef(initialLimit);

  const fetchPage = useCallback(async (reset = false) => {
    try {
      setLoading(true);
      if (reset) {
        offsetRef.current = 0;
      }
      const url = `/api/sessions?limit=${limitRef.current}&offset=${offsetRef.current}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Failed sessions page: ${res.status}`);
      const data = await res.json();
      const mapped = data.map(s => ({ ...s, files: [] }));
      setSessions(prev => reset ? mapped : [...prev, ...mapped]);
      // If fewer than requested returned, no more pages
      setHasMore(data.length === limitRef.current);
      offsetRef.current += data.length;
      setError(null);
    } catch (e) {
      console.error('fetchPage error', e);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadMore = useCallback(async () => {
    if (loading || !hasMore) return;
    await fetchPage(false);
  }, [fetchPage, loading, hasMore]);

  const reset = useCallback(async () => {
    setSessions([]);
    setHasMore(true);
    await fetchPage(true);
  }, [fetchPage]);

  const loadSessionFiles = useCallback(async (sessionId, limit = 200, offset = 0) => {
    const target = sessions.find(s => s.id === sessionId);
    if (!target) return;
    // If already loaded first page and offset==0, skip
    if (target.files && target.files.length > 0 && offset === 0) return;
    try {
      const res = await fetch(`/api/sessions/${sessionId}/files?limit=${limit}&offset=${offset}`);
      if (!res.ok) throw new Error(`Failed files for session ${sessionId}`);
      const files = await res.json();
      setSessions(prev => prev.map(s => s.id === sessionId ? {
        ...s,
        files: offset > 0 ? [...(s.files||[]), ...files] : files
      } : s));
    } catch (e) {
      console.warn('loadSessionFiles error', e);
    }
  }, [sessions]);

  return {
    sessions,
    loading,
    error,
    hasMore,
    loadMore,
    reset,
    loadSessionFiles,
  };
}
