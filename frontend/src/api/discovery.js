import { useQuery } from '@tanstack/react-query';
import { httpJson, clearEtagCache } from '../data/http';

/**
 * Hook to fetch FTP discovery diagnostic information
 * 
 * Returns detailed info about files found on FTP and why they
 * are or aren't being added to sessions.
 * 
 * @param {Object} options - Query options
 * @param {boolean} options.enabled - Whether to run the query
 * @returns {UseQueryResult} React Query result with diagnostic data
 */
export function useFTPDiagnose(options = {}) {
  return useQuery({
    queryKey: ['ftp-diagnose'],
    queryFn: async () => {
      // Clear any cached ETag for this endpoint to ensure fresh FTP scan
      clearEtagCache('/api/discovery/diagnose');
      return httpJson('/api/discovery/diagnose');
    },
    staleTime: 0, // Always refetch - diagnostic data should be fresh
    gcTime: 0, // Don't cache
    enabled: options.enabled ?? false, // Disabled by default - run on demand
    retry: false, // Don't retry on failure
  });
}

/**
 * Hook to fetch discovery status (FTP config, last discovery, auto-scan status)
 * @param {Object} options - Query options
 * @param {boolean} options.enabled - Whether to run the query (default: true)
 * @param {number} options.refetchInterval - Auto-refetch interval in ms (default: 5000 for live updates)
 * @returns {UseQueryResult} React Query result
 */
export function useDiscoveryStatus(options = {}) {
  return useQuery({
    queryKey: ['discovery-status'],
    queryFn: () => httpJson('/api/discovery/status'),
    staleTime: 2_000, // 2 seconds - allow frequent updates for auto-scan status
    refetchInterval: options.refetchInterval ?? 5_000, // Refetch every 5 seconds by default
    enabled: options.enabled ?? true,
  });
}

/**
 * File status codes returned by the diagnostic endpoint
 */
export const FileStatus = {
  ADDED: 'added',
  EXISTS: 'exists',
  EXCLUDED: 'excluded',
  HIDDEN: 'hidden',
  SYSTEM: 'system',
  WRONG_EXTENSION: 'wrong_extension',
  TOO_SMALL: 'too_small',
  INVALID_NAME: 'invalid_name',
};

/**
 * Human-readable labels for file status codes
 */
export const FileStatusLabels = {
  [FileStatus.ADDED]: 'Will Add',
  [FileStatus.EXISTS]: 'Already Added',
  [FileStatus.EXCLUDED]: 'Excluded Folder',
  [FileStatus.HIDDEN]: 'Hidden File',
  [FileStatus.SYSTEM]: 'System File',
  [FileStatus.WRONG_EXTENSION]: 'Wrong Extension',
  [FileStatus.TOO_SMALL]: 'Too Small (<5MB)',
  [FileStatus.INVALID_NAME]: 'Invalid Filename',
};

/**
 * Color classes for file status badges
 */
export const FileStatusColors = {
  [FileStatus.ADDED]: 'bg-green-100 text-green-800',
  [FileStatus.EXISTS]: 'bg-blue-100 text-blue-800',
  [FileStatus.EXCLUDED]: 'bg-orange-100 text-orange-800',
  [FileStatus.HIDDEN]: 'bg-gray-100 text-gray-600',
  [FileStatus.SYSTEM]: 'bg-gray-100 text-gray-600',
  [FileStatus.WRONG_EXTENSION]: 'bg-yellow-100 text-yellow-800',
  [FileStatus.TOO_SMALL]: 'bg-red-100 text-red-800',
  [FileStatus.INVALID_NAME]: 'bg-red-100 text-red-800',
};
