import { useEffect, useRef, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useWebSocket } from './useWebSocket';
import { WORKER_STATUS_QUERY_KEY } from '../api/workers';

const IS_DEV = process.env.NODE_ENV === 'development';
const MAX_PROCESSED_IDS = 1000; // Ring buffer size for message deduplication

/**
 * Centralized WebSocket message handler
 * 
 * Updates TanStack Query cache directly in response to WebSocket events.
 * Eliminates the need for a separate Zustand store.
 */
export function useWebSocketMessages() {
  const { lastMessage, connected } = useWebSocket();
  const queryClient = useQueryClient();
  const processedIds = useRef(new Set());

  // Throttled refetch for structural changes
  const throttledRefetch = useRef(null);
  const lastRefetchTime = useRef(0);

  const triggerStructuralRefetch = useCallback(() => {
    const now = Date.now();
    const timeSinceLastRefetch = now - lastRefetchTime.current;

    if (timeSinceLastRefetch < 5000) {
      if (throttledRefetch.current) clearTimeout(throttledRefetch.current);
      throttledRefetch.current = setTimeout(() => {
        if (IS_DEV) console.log('🔄 Throttled structural refetch');
        queryClient.invalidateQueries({ queryKey: ['sessions'] });
        lastRefetchTime.current = Date.now();
      }, 5000 - timeSinceLastRefetch);
    } else {
      if (IS_DEV) console.log('🔄 Structural change detected, invalidating sessions...');
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
      lastRefetchTime.current = now;
    }
  }, [queryClient]);

  useEffect(() => {
    if (!lastMessage) return;

    // Deduplicate messages
    const messageId = lastMessage.id || `${lastMessage.type}-${Date.now()}-${Math.random()}`;
    if (processedIds.current.has(messageId)) return;

    processedIds.current.add(messageId);
    if (processedIds.current.size > MAX_PROCESSED_IDS) {
      const arr = Array.from(processedIds.current);
      processedIds.current = new Set(arr.slice(-MAX_PROCESSED_IDS));
    }

    handleMessage(lastMessage, queryClient, triggerStructuralRefetch);

  }, [lastMessage, queryClient, triggerStructuralRefetch]);

  // Cleanup
  useEffect(() => {
    return () => {
      if (throttledRefetch.current) clearTimeout(throttledRefetch.current);
    };
  }, []);

  return { connected };
}

function handleMessage(message, queryClient, triggerStructuralRefetch) {
  if (IS_DEV) console.log('📨 WebSocket message:', message.type);

  const data = message.data || message;

  // Helper to update session list
  const updateSessionList = (updater) => {
    queryClient.setQueryData(['sessions'], (oldSessions) => {
      if (!oldSessions) return oldSessions;
      return updater(oldSessions);
    });
  };

  // Helper to update file in a specific session
  const updateFileInSession = (sessionId, fileId, fileUpdater) => {
    queryClient.setQueryData(['session-files', sessionId], (oldFiles) => {
      if (!oldFiles) return oldFiles;
      // API returns array of files directly
      return oldFiles.map(f => f.id === fileId ? { ...f, ...fileUpdater(f) } : f);
    });
  };

  // Helper to find session for a file (expensive, use sparingly)
  const findSessionIdForFile = (fileId) => {
    const queries = queryClient.getQueriesData({ queryKey: ['session-files'] });
    for (const [queryKey, files] of queries) {
      if (Array.isArray(files) && files.find(f => f.id === fileId)) {
        return queryKey[1]; // session-files, sessionId
      }
    }
    return null;
  };

  switch (message.type) {
    case 'batch':
      message.messages?.forEach(msg => handleMessage(msg, queryClient, triggerStructuralRefetch));
      break;

    case 'file_state_change':
      if (data.file_id) {
        // Use provided session_id, or fallback to looking up the session
        let sessionId = data.session_id;
        if (!sessionId) {
          sessionId = findSessionIdForFile(data.file_id);
          if (IS_DEV && !sessionId) {
            console.warn(`⚠️ file_state_change received without session_id for file ${data.file_id}`);
          }
        }
        
        if (sessionId) {
          updateFileInSession(sessionId, data.file_id, (f) => ({
            state: data.state,
            progress_pct: data.progress_pct,
            error_message: data.error_message,
            progress_stage: data.progress_stage,
            copy_speed_mbps: data.copy_speed_mbps,
            jobs: f.jobs ? f.jobs.map((j, idx) => idx === f.jobs.length - 1 ? { ...j, progress_pct: data.progress_pct, progress_stage: data.progress_stage } : j) : f.jobs
          }));

          // Also update primary file state in session list if applicable
          updateSessionList(sessions => sessions.map(s => {
            if (s.id === sessionId && s.primary_file_id === data.file_id) {
              return { ...s, primary_file_state: data.state };
            }
            return s;
          }));
        }
      }
      break;

    case 'job_progress':
      if (data.session_id) {
        // We might not have file_id here, but usually job_progress is less critical for file list
        // unless we want to update the session progress bar if we had one.
        // But we can try to find the file if needed.
        // For now, just update session summary if needed? No, session summary doesn't have job progress.
      }
      break;

    case 'session.file_added':
    case 'file_added':
      if (data.session_id && data.file_data) {
        queryClient.setQueryData(['session-files', data.session_id], (oldFiles) => {
          if (!oldFiles) return [data.file_data];
          if (oldFiles.find(f => f.id === data.file_data.id)) return oldFiles;
          return [...oldFiles, data.file_data];
        });
        // Update session file count
        updateSessionList(sessions => sessions.map(s =>
          s.id === data.session_id ? { ...s, file_count: (s.file_count || 0) + 1 } : s
        ));
      }
      break;

    case 'processing_substep':
      if (data.file_id) {
        // Use provided session_id, or fallback to looking up the session
        const substepSessionId = data.session_id || findSessionIdForFile(data.file_id);
        if (substepSessionId) {
          updateFileInSession(substepSessionId, data.file_id, () => ({
            substep: data.substep,
            progress: data.progress,
            detail: data.detail
          }));
        }
      }
      break;

    case 'analytics.state':
      if (data.file_id) {
        const sessionId = findSessionIdForFile(data.file_id);
        if (sessionId) {
          updateFileInSession(sessionId, data.file_id, () => ({
            analytics_state: data.state,
            ...(data.title && { title: data.title }),
            ...(data.language && { language: data.language }),
            ...(data.error && { analytics_error: data.error }),
            ...(data.can_retry !== undefined && { analytics_can_retry: data.can_retry })
          }));
        }
        
        // Show alert for OOM errors
        if (data.state === 'OOM_ERROR') {
          const filename = data.filename || 'file';
          setTimeout(() => {
            alert(`⚠️ Out of Memory\n\nAnalysis of "${filename}" ran out of memory.\n\nClose other applications to free up memory, then try again.`);
          }, 100);
        }
      }
      break;

    case 'thumbnail_update':
      if (data.file_id) {
        const sessionId = findSessionIdForFile(data.file_id);
        if (sessionId) {
          updateFileInSession(sessionId, data.file_id, () => ({
            thumbnail_state: data.thumbnail_state,
            etag: data.etag,
            thumbnail_error: data.error
          }));
        }
      }
      break;

    case 'session.created':
    case 'session.updated':
    case 'session_discovered':
      if (data.session || data.session_id) {
        const sessionData = data.session || {
          id: data.session_id,
          name: data.session_name,
          file_count: data.file_count,
          discovered_at: new Date().toISOString() // Fallback
        };
        updateSessionList(sessions => {
          const exists = sessions.find(s => s.id === sessionData.id);
          if (exists) return sessions.map(s => s.id === sessionData.id ? { ...s, ...sessionData } : s);
          return [sessionData, ...sessions];
        });
        // For new sessions, also trigger refetch to get complete session data
        // Uses throttling to avoid excessive queries during bulk discovery
        if (message.type === 'session_discovered' || message.type === 'session.created') {
          triggerStructuralRefetch();
        }
      }
      break;

    case 'session.deleted':
      if (data.session_id) {
        updateSessionList(sessions => sessions.filter(s => s.id !== data.session_id));
        queryClient.removeQueries({ queryKey: ['session-files', data.session_id] });
      }
      break;

    case 'discovery.complete':
    case 'bulk_import.complete':
      triggerStructuralRefetch();
      break;

    case 'error':
      console.error('WebSocket error message:', data.error_message || data.message);
      // Show alert for specific error types that need user attention
      if (data.error_type === 'analysis_oom') {
        const filename = data.context?.filename || 'file';
        setTimeout(() => {
          alert(`⚠️ Out of Memory\n\n${data.error_message}\n\nThe file can be re-analyzed after freeing up memory.`);
        }, 100);
      }
      break;

    case 'worker_status':
      // DIRECTLY update the React Query cache
      // This triggers an immediate re-render of the WorkerStatus component
      queryClient.setQueryData(WORKER_STATUS_QUERY_KEY, {
        workers: data.workers,
        queue_counts: data.queue_counts,
        paused: data.paused,
        timestamp: Date.now() / 1000
      });
      break;
  }
}
