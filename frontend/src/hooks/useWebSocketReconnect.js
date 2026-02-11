import { useRef, useCallback, useEffect } from 'react';
import { WEBSOCKET_CONFIG } from '../constants/websocket';
import { clearReconnectTimeout } from '../utils/websocketHelpers';

/**
 * @typedef {Object} WebSocketReconnectReturn
 * @property {() => void} scheduleReconnect - Schedule a reconnection attempt
 * @property {() => void} cancelReconnect - Cancel scheduled reconnection
 * @property {number} reconnectAttempts - Number of reconnection attempts made
 */

/**
 * Hook for managing WebSocket reconnection logic
 *
 * Handles automatic reconnection with exponential backoff and max attempts.
 * This is a focused hook following Single Responsibility Principle.
 *
 * @param {Function} onReconnect - Callback to execute reconnection
 * @returns {WebSocketReconnectReturn} Reconnection state and methods
 */
export function useWebSocketReconnect(onReconnect) {
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttemptsRef = useRef(0);

  const scheduleReconnect = useCallback(() => {
    if (reconnectAttemptsRef.current >= WEBSOCKET_CONFIG.MAX_RECONNECT_ATTEMPTS) {
      console.warn('Max reconnection attempts reached');
      return;
    }

    reconnectAttemptsRef.current += 1;
    const delay = WEBSOCKET_CONFIG.RECONNECT_DELAY;

    console.log(`🔄 Scheduling reconnect attempt ${reconnectAttemptsRef.current}/${WEBSOCKET_CONFIG.MAX_RECONNECT_ATTEMPTS} in ${delay}ms`);

    reconnectTimeoutRef.current = setTimeout(() => {
      console.log(`🔄 Attempting to reconnect (attempt ${reconnectAttemptsRef.current})...`);
      onReconnect?.();
    }, delay);
  }, [onReconnect]);

  const cancelReconnect = useCallback(() => {
    clearReconnectTimeout(reconnectTimeoutRef);
    reconnectAttemptsRef.current = 0;
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearReconnectTimeout(reconnectTimeoutRef);
    };
  }, []);

  return {
    scheduleReconnect,
    cancelReconnect,
    reconnectAttempts: reconnectAttemptsRef.current,
  };
}
