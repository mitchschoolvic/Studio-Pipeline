import { useQuery } from '@tanstack/react-query';
import { httpJson } from '../data/http';

export const WORKER_STATUS_QUERY_KEY = ['worker-status'];

/**
 * Hook to fetch real-time worker status.
 * Data is initially fetched via HTTP, then kept fresh via WebSockets
 * (managed globally) or fallback polling.
 */
export function useWorkerStatus() {
    return useQuery({
        queryKey: WORKER_STATUS_QUERY_KEY,
        queryFn: () => httpJson('/api/workers/status'),
        // Fallback polling every 5s in case WebSocket drops, 
        // but don't poll aggressively (let WS drive updates)
        refetchInterval: 5000,
        staleTime: 10000, // Data is considered fresh for 10s
        initialData: {
            workers: [],
            queue_counts: {},
            paused: { processing: false, analytics: false },
            timestamp: Date.now() / 1000
        }
    });
}
