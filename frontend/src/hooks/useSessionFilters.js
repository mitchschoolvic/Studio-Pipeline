import { useMemo } from 'react';
import { filterSessions, sortSessions } from '../utils/sessionFilters';

/**
 * useSessionFilters Hook
 * 
 * Combines filtering and sorting logic with memoization for performance.
 * Prevents unnecessary re-filtering/re-sorting on every render.
 * 
 * @param {Array} sessions - Array of session objects
 * @param {string} searchTerm - Search term for filtering
 * @param {string} sortOption - Sort option (from SORT_OPTIONS)
 * @returns {Array} Filtered and sorted sessions
 * 
 * @example
 * const displayedSessions = useSessionFilters(sessions, searchTerm, 'newest')
 */
export function useSessionFilters(sessions, searchTerm, sortOption) {
  // First, filter sessions based on search term
  const filteredSessions = useMemo(() => {
    return filterSessions(sessions, searchTerm);
  }, [sessions, searchTerm]);

  // Then, sort the filtered results
  const sortedSessions = useMemo(() => {
    return sortSessions(filteredSessions, sortOption);
  }, [filteredSessions, sortOption]);

  return sortedSessions;
}
