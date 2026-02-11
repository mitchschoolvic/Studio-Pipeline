import { useState, useEffect, useRef, useCallback } from 'react';
import { VariableSizeList as List } from 'react-window';
import AutoSizer from 'react-virtualized-auto-sizer';
import { useWebSocket } from '../hooks/useWebSocket';
import { useSessions } from '../contexts/SessionsContext';
import { PipelineSessionCard } from './PipelineSessionCard';

/**
 * SessionList Component
 *
 * Displays a list of recording sessions from the Studio Pipeline.
 * Shows session name, date, file count, and total size.
 */
export function SessionList() {
  const { sessions, fetchSessions } = useSessions();
  const { connected } = useWebSocket();
  const [expandedSessions, setExpandedSessions] = useState(new Set());
  const listRef = useRef(null);

  // Calculate item size based on whether session is expanded
  const getItemSize = useCallback((index) => {
    const session = sessions[index];
    if (!session) return 110; // Default collapsed height
    
    const isExpanded = expandedSessions.has(session.id);
    if (!isExpanded) return 110; // Collapsed height
    
    // Expanded height - use a generous default to accommodate files loading
    // Most sessions have 1 program file + 8 ISO cameras
    const baseHeight = 110; // Header
    const programFileHeight = 120; // Program file section
    
    // Estimate ISO files: if session.files exists, use actual count; otherwise assume typical 8 cameras
    const isoFilesCount = session.files?.filter(f => f.is_iso).length || 8;
    const isoFilesHeight = isoFilesCount > 0 ? 80 + Math.ceil(isoFilesCount / 4) * 180 : 0; // Grid layout
    
    return baseHeight + programFileHeight + isoFilesHeight + 60; // +60 for padding and loading state
  }, [sessions, expandedSessions]);

  // Handle session expansion toggle
  const handleToggleExpand = useCallback((sessionId) => {
    setExpandedSessions(prev => {
      const newSet = new Set(prev);
      if (newSet.has(sessionId)) {
        newSet.delete(sessionId);
      } else {
        newSet.add(sessionId);
      }
      return newSet;
    });
    
    // Reset list item sizes after expansion state changes
    if (listRef.current) {
      listRef.current.resetAfterIndex(0);
    }
  }, []);

  const loading = sessions.length === 0;
  const error = null;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-500 rounded-lg p-4">
        <p className="text-red-400">Error: {error}</p>
        <button
          onClick={() => reset()}
          className="mt-2 px-4 py-2 bg-red-600 hover:bg-red-700 rounded text-white"
        >
          Retry
        </button>
      </div>
    );
  }

  if (sessions.length === 0) {
    return (
      <div className="text-center py-12 text-gray-400">
        <p className="text-lg">No sessions found</p>
        <p className="text-sm mt-2">Sessions will appear here when files are discovered from FTP</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-2xl font-bold text-white">Recording Sessions</h2>
          {/* Live Connection Indicator */}
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500 animate-pulse' : 'bg-gray-500'}`} />
            <span className="text-xs text-gray-400">
              {connected ? 'Live updates active' : 'Disconnected'}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => fetchSessions({ replace: true })}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-white transition-colors"
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="h-[60vh]">
        <AutoSizer disableWidth>
          {({ height }) => (
            <List
              ref={listRef}
              height={height}
              itemCount={sessions.length}
              itemSize={getItemSize}
              width={'100%'}
            >
              {({ index, style }) => {
                const session = sessions[index];
                const isExpanded = expandedSessions.has(session.id);
                return (
                  <div style={style}>
                    <PipelineSessionCard 
                      key={session.id}
                      session={session}
                      isExpanded={isExpanded}
                      onToggleExpand={() => handleToggleExpand(session.id)}
                      onFilesLoaded={() => {
                        // Recalculate heights after files load
                        if (listRef.current) {
                          listRef.current.resetAfterIndex(index);
                        }
                      }}
                    />
                  </div>
                );
              }}
            </List>
          )}
        </AutoSizer>
      </div>
    </div>
  );
}
