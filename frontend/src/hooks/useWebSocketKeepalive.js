import { useRef, useCallback, useEffect } from 'react';
import { WEBSOCKET_CONFIG } from '../constants/websocket';
import { clearPingInterval } from '../utils/websocketHelpers';

/**
 * @typedef {Object} WebSocketKeepaliveReturn
 * @property {() => void} startKeepalive - Start sending ping messages
 * @property {() => void} stopKeepalive - Stop sending ping messages
 */

/**
 * Hook for managing WebSocket keepalive (ping/pong)
 *
 * Sends periodic ping messages to keep connection alive.
 * This is a focused hook following Single Responsibility Principle.
 *
 * @param {Function} sendPing - Function to send ping message
 * @returns {WebSocketKeepaliveReturn} Keepalive control methods
 */
export function useWebSocketKeepalive(sendPing) {
  const pingIntervalRef = useRef(null);

  const startKeepalive = useCallback(() => {
    // Clear any existing interval
    if (pingIntervalRef.current) {
      clearPingInterval(pingIntervalRef);
    }

    pingIntervalRef.current = setInterval(() => {
      sendPing?.();
    }, WEBSOCKET_CONFIG.PING_INTERVAL);
  }, [sendPing]);

  const stopKeepalive = useCallback(() => {
    clearPingInterval(pingIntervalRef);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearPingInterval(pingIntervalRef);
    };
  }, []);

  return {
    startKeepalive,
    stopKeepalive,
  };
}
