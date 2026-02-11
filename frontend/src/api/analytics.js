import { useQuery } from '@tanstack/react-query';
import { httpJson } from '../data/http';

/**
 * Safe fetch wrapper that returns null for 404 errors
 * Used for analytics endpoints that may not exist in standard builds
 */
async function safeHttpJson(url) {
  try {
    const res = await fetch(url);
    if (res.status === 404) {
      return null;
    }
    if (!res.ok) {
      throw new Error(`HTTP error: ${res.status}`);
    }
    return await res.json();
  } catch (error) {
    console.debug(`Analytics endpoint ${url} not available:`, error.message);
    return null;
  }
}

/**
 * Fetch aggregated analytics charts data
 * Returns null if analytics features are not available
 * @param {string} timeRange - Time range filter (all, 2025, 12m, 30d, etc.)
 * @returns {Promise<Object|null>} Charts data or null if not available
 */
export async function fetchAnalyticsCharts(timeRange = 'all') {
  return safeHttpJson(`/api/analytics/charts?time_range=${timeRange}`);
}

/**
 * Fetch drill-down data for a specific chart segment
 * Returns null if analytics features are not available
 * @param {string} timeRange - Time range filter
 * @param {string} type - Filter type (audience, faculty, etc.)
 * @param {string} value - Filter value (Parents, Science, etc.)
 * @returns {Promise<Array|null>} List of matching files or null
 */
export async function fetchAnalyticsDrilldown(timeRange, type, value) {
  const params = new URLSearchParams({
    time_range: timeRange,
    filter_type: type,
    filter_value: value,
    limit: 100 // Safe default
  });
  return safeHttpJson(`/api/analytics/drilldown?${params.toString()}`);
}

/**
 * Hook to fetch drilldown data for a specific chart segment
 * Uses the dedicated /drilldown endpoint which handles mapping context to queries
 * Returns null if analytics features are not available
 */
export function useAnalyticsDrilldown(timeRange, filterType, filterValue) {
  return useQuery({
    queryKey: ['analytics-drilldown', timeRange, filterType, filterValue],
    queryFn: async () => {
      const params = new URLSearchParams({
        time_range: timeRange,
        filter_type: filterType,
        filter_value: filterValue,
        limit: 1000
      });
      return safeHttpJson(`/api/analytics/drilldown?${params.toString()}`);
    },
    // Only fetch if we have valid filters
    enabled: !!filterType && !!filterValue,
    retry: false,
  });
}

/**
 * Hook to fetch analytics summary list
 * Returns null if analytics features are not available
 * @param {Object} params - Query parameters (page, pageSize, sort, state, q)
 * @returns {UseQueryResult} React Query result
 */
export function useAnalyticsSummary(params = {}) {
  const { page = 0, pageSize = 50, sort, state, q, faculty, content_type, speaker_count, start_date, end_date, audience, speaker_type } = params;

  const queryParams = new URLSearchParams();
  if (state) queryParams.append('state', state);
  if (q) queryParams.append('q', q);
  if (faculty) queryParams.append('faculty', faculty);
  if (content_type) queryParams.append('content_type', content_type);
  if (speaker_count !== undefined) queryParams.append('speaker_count', speaker_count);
  if (start_date) queryParams.append('start_date', start_date);
  if (end_date) queryParams.append('end_date', end_date);
  if (audience) queryParams.append('audience', audience);
  if (speaker_type) queryParams.append('speaker_type', speaker_type);

  // Map page/pageSize to limit/offset
  queryParams.append('limit', pageSize);
  queryParams.append('offset', page * pageSize);

  if (sort) queryParams.append('sort', sort);

  return useQuery({
    queryKey: ['analytics-summary', params],
    queryFn: () => safeHttpJson(`/api/analytics/summary?${queryParams.toString()}`),
    placeholderData: (previousData) => previousData, // Keep previous data while fetching new page
    retry: false,
  });
}

/**
 * Hook to fetch full analytics detail
 * Returns null if analytics features are not available
 * @param {string} analyticsId - Analytics ID
 * @returns {UseQueryResult} React Query result
 */
export function useAnalyticsDetail(analyticsId) {
  return useQuery({
    queryKey: ['analytics-detail', analyticsId],
    queryFn: () => safeHttpJson(`/api/analytics/detail/${analyticsId}`),
    enabled: !!analyticsId,
    retry: false,
  });
}