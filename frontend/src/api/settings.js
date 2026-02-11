import { useQuery, useMutation } from '@tanstack/react-query';
import { httpJson } from '../data/http';
import { queryClient } from '../data/client';

/**
 * Hook to fetch main application settings (FTP, pipeline, etc.)
 * @returns {UseQueryResult} React Query result
 */
export function useSettings() {
  return useQuery({
    queryKey: ['settings-main'],
    queryFn: () => httpJson('/api/settings'),
    staleTime: 60_000, // 1 minute
  });
}

/**
 * Hook to update main application settings
 * @returns {UseMutationResult} React Query mutation result
 */
export function useSaveSettings() {
  return useMutation({
    mutationFn: ({ key, value }) =>
      fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key, value }),
      }).then((r) => r.json()),
    onSuccess: () => {
      // Invalidate settings cache to refetch
      queryClient.invalidateQueries({ queryKey: ['settings-main'] });
    },
  });
}

/**
 * Safe fetch wrapper that returns null for 404 errors (endpoint not available)
 * Used for optional AI endpoints that may not exist in standard builds
 */
async function safeHttpJson(url) {
  try {
    const res = await fetch(url);
    if (res.status === 404) {
      // Endpoint not available (standard build without AI)
      return null;
    }
    if (!res.ok) {
      throw new Error(`HTTP error: ${res.status}`);
    }
    return await res.json();
  } catch (error) {
    console.debug(`Optional endpoint ${url} not available:`, error.message);
    return null;
  }
}

/**
 * Hook to fetch AI model availability info
 * Returns null if AI features are not available (standard build)
 * @returns {UseQueryResult} React Query result
 */
export function useAiInfo() {
  return useQuery({
    queryKey: ['ai-info'],
    queryFn: () => safeHttpJson('/api/analytics/info'),
    staleTime: 5 * 60_000, // 5 minutes - AI info rarely changes
    retry: false, // Don't retry if endpoint doesn't exist
  });
}

/**
 * Hook to fetch LLM prompts (system and user)
 * Returns null if AI features are not available
 * @returns {UseQueryResult} React Query result
 */
export function usePrompts() {
  return useQuery({
    queryKey: ['settings-prompts'],
    queryFn: () => safeHttpJson('/api/analytics/prompts'),
    staleTime: 60_000, // 1 minute - settings don't change often
    retry: false,
  });
}

/**
 * Hook to update LLM prompts
 * @returns {UseMutationResult} React Query mutation result
 */
export function useSavePrompts() {
  return useMutation({
    mutationFn: (patch) =>
      fetch('/api/analytics/prompts', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      }).then((r) => r.json()),
    onSuccess: (data) => {
      // Update cache with new data
      queryClient.setQueryData(['settings-prompts'], {
        system_prompt: data.system_prompt,
        user_prompt: data.user_prompt,
      });
    },
  });
}

/**
 * Hook to fetch Whisper transcription settings
 * Returns null if AI features are not available
 * @returns {UseQueryResult} React Query result
 */
export function useWhisperSettings() {
  return useQuery({
    queryKey: ['settings-whisper'],
    queryFn: () => safeHttpJson('/api/analytics/whisper-settings'),
    staleTime: 60_000, // 1 minute
    retry: false,
  });
}

/**
 * Hook to update Whisper settings
 * @returns {UseMutationResult} React Query mutation result
 */
export function useSaveWhisperSettings() {
  return useMutation({
    mutationFn: (settings) =>
      fetch('/api/analytics/whisper-settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ settings }),
      }).then((r) => r.json()),
    onSuccess: (data) => {
      // Update cache with new data
      queryClient.setQueryData(['settings-whisper'], data);
    },
  });
}

/**
 * Hook to toggle analytics pause
 * No-op if AI features are not available
 * @returns {UseMutationResult} React Query mutation result
 */
export function useToggleAnalyticsPause() {
  return useMutation({
    mutationFn: async () => {
      const res = await fetch('/api/analytics/toggle-pause', { method: 'POST' });
      if (res.status === 404) return null;
      return res.json();
    },
    onSuccess: () => {
      // Invalidate analytics stats to show updated pause status
      queryClient.invalidateQueries({ queryKey: ['analytics-stats'] });
      queryClient.invalidateQueries({ queryKey: ['analytics-pause-status'] });
    },
  });
}

/**
 * Hook to get analytics pause status
 * Returns null if AI features are not available
 * @returns {UseQueryResult} React Query result
 */
export function useAnalyticsPauseStatus() {
  return useQuery({
    queryKey: ['analytics-pause-status'],
    queryFn: () => safeHttpJson('/api/analytics/pause-status'),
    staleTime: 10_000, // 10 seconds
    refetchInterval: 10_000, // Poll every 10 seconds
    retry: false,
  });
}

/**
 * Hook to get/set run when idle setting
 * Returns null if AI features are not available
 * @returns {UseQueryResult} React Query result
 */
export function useRunWhenIdleSetting() {
  return useQuery({
    queryKey: ['settings-run-when-idle'],
    queryFn: () => safeHttpJson('/api/analytics/settings/run-when-idle'),
    staleTime: 60_000,
    retry: false,
  });
}

/**
 * Hook to update run when idle setting
 * No-op if AI features are not available
 * @returns {UseMutationResult} React Query mutation result
 */
export function useSaveRunWhenIdleSetting() {
  return useMutation({
    mutationFn: async (enabled) => {
      const res = await fetch('/api/analytics/settings/run-when-idle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      });
      if (res.status === 404) return null;
      return res.json();
    },
    onSuccess: (data) => {
      if (data) {
        queryClient.setQueryData(['settings-run-when-idle'], data);
      }
    },
  });
}
